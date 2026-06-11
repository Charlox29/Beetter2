"""
beehive/data.py
─────────────────────────────────────────────────────────────────────────────
Everything that touches raw data before it reaches the model.

Contents:
  decode_packet()          – unpack 31 raw bytes into a physical-unit dict
  packet_to_raw_features() – convert that dict into two (9,) numpy arrays
  FeatureNormalizer        – fit/transform/save/load z-score statistics
  BeehiveDataset           – unlabelled dataset for CMC pre-training
  LabeledBeehiveDataset    – labelled dataset for SupCon fine-tuning
  BalancedClassSampler     – over/under-samples to keep batch class distribution even

Feature vector layout (same for inside and outside):
  [0] temperature   (°C, z-scored)
  [1] humidity      (%, z-scored)
  [2] log(RMS)      (log applied FIRST, then z-scored — see note below)
  [3] dom_freq      (Hz, z-scored)
  [4] mfcc_1  ┐
  [5] mfcc_2  │  each coefficient has its OWN μ and σ (per-coefficient z-score)
  [6] mfcc_3  │  because MFCC coefficients have very different natural scales:
  [7] mfcc_4  │  C1 might range −30 to +30; C5 might range −3 to +3
  [8] mfcc_5  ┘

NOTE on log(RMS):
  RMS values are strictly positive and span several orders of magnitude
  (e.g. 0.001 for a quiet hive, 0.3 for a noisy one). This log-scale behaviour
  means a standard z-score would be dominated by rare loud events. Applying
  log() first maps multiplicative differences to additive ones, making the
  distribution approximately Gaussian before z-scoring.
  The ESP32 stores log10(RMS)×16 in the packet; we invert back to physical
  RMS in decode_packet() and re-apply natural log here for consistency.
"""

from __future__ import annotations

import json
import struct
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset, Sampler

from .config import LORA_PKT_CFG, HIVE_STATES, NUM_CLASSES

logger = logging.getLogger(__name__)

# ── Packet decoder ────────────────────────────────────────────────────────────

# Pre-compiled struct for speed (decode_packet is called on every packet)
_PACKET_STRUCT = struct.Struct(LORA_PKT_CFG.struct_fmt)
assert _PACKET_STRUCT.size == LORA_PKT_CFG.size_bytes, (
    f"Struct size mismatch: expected {LORA_PKT_CFG.size_bytes}, "
    f"got {_PACKET_STRUCT.size}. Check config.py struct_fmt."
)


def decode_packet(raw: bytes) -> dict:
    """
    Unpack a 31-byte LoRa binary payload into a dict of physical-unit values.

    All integer scaling from the ESP32 firmware is inverted here so that
    the rest of the pipeline works in familiar units (°C, %, Hz, etc.).

    Args:
        raw: 31 bytes exactly, as received from the LoRa gateway.

    Returns:
        Dict with keys: timestamp_min, t_in_C, t_out_C, h_in_pct, h_out_pct,
        rms_in, rms_out, dom_freq_in_hz, dom_freq_out_hz, mfcc_in (list[5]),
        mfcc_out (list[5]), anomaly_flag.
    """
    if len(raw) != LORA_PKT_CFG.size_bytes:
        raise ValueError(
            f"Expected {LORA_PKT_CFG.size_bytes} bytes, got {len(raw)}"
        )

    (ts,
     t_in, t_out,
     h_in, h_out,
     lr_in, lr_out,         # log10(RMS)×16, int8
     df_in, df_out,         # Hz÷10, uint8
     mi1, mi2, mi3, mi4, mi5,   # MFCC inside ×10, int16
     mo1, mo2, mo3, mo4, mo5,   # MFCC outside ×10, int16
     flag) = _PACKET_STRUCT.unpack(raw)

    return {
        "timestamp_min":    ts,
        "t_in_C":           float(t_in),
        "t_out_C":          float(t_out),
        "h_in_pct":         float(h_in),
        "h_out_pct":        float(h_out),
        # Invert log10(RMS)×16 → physical RMS
        "rms_in":           10.0 ** (lr_in  / 16.0),
        "rms_out":          10.0 ** (lr_out / 16.0),
        # Invert Hz÷10 → Hz
        "dom_freq_in_hz":   df_in  * 10.0,
        "dom_freq_out_hz":  df_out * 10.0,
        # Invert ×10 scaling
        "mfcc_in":  [mi1 / 10.0, mi2 / 10.0, mi3 / 10.0, mi4 / 10.0, mi5 / 10.0],
        "mfcc_out": [mo1 / 10.0, mo2 / 10.0, mo3 / 10.0, mo4 / 10.0, mo5 / 10.0],
        "anomaly_flag": flag,
    }


def packet_to_raw_features(
    packet: dict,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert a decoded packet dict into two (9,) float32 arrays.

    Note: log(RMS) is applied here (natural log, not log10).
    The FeatureNormalizer will then z-score the full 9-d vector, including
    the log(RMS) dimension.

    Returns:
        (vec_in, vec_out): both shape (9,), float32, UN-normalised.
    """
    def build(t, h, rms, freq, mfccs):
        return np.array([
            t,
            h,
            np.log(max(rms, 1e-12)),  # log(RMS) — must stay negative for very quiet hives
            freq,
            *mfccs,
        ], dtype=np.float32)

    vec_in  = build(packet["t_in_C"],  packet["h_in_pct"],
                    packet["rms_in"],  packet["dom_freq_in_hz"],  packet["mfcc_in"])
    vec_out = build(packet["t_out_C"], packet["h_out_pct"],
                    packet["rms_out"], packet["dom_freq_out_hz"], packet["mfcc_out"])
    return vec_in, vec_out


# ── Feature normalizer ────────────────────────────────────────────────────────

class FeatureNormalizer:
    """
    Per-feature z-score normalisation: x_norm = (x − μ) / σ

    Create one instance for the INSIDE sensor and one for the OUTSIDE sensor.
    They live in different physical environments so their distributions differ.

    Calibration workflow (do this once, at the start of a season):
    ─────────────────────────────────────────────────────────────
    1. Collect 2–4 weeks of packets (>2000 samples is ideal).
    2. Call fit() on the inside and outside raw feature arrays.
    3. Save with save(). The JSON files are then FROZEN.
    4. Load with FeatureNormalizer.load() at inference time.

    Why freeze instead of updating online?
    ───────────────────────────────────────
    If μ and σ silently drift (e.g., seasonal temperature shift), the model
    input distribution changes without any change to weights. This is one of
    the hardest bugs to notice in production. Freezing forces an explicit
    recalibration decision at the start of each season.
    """

    N_FEATURES = 9
    FEATURE_NAMES = [
        "temperature", "humidity", "log_rms", "dom_freq",
        "mfcc_1", "mfcc_2", "mfcc_3", "mfcc_4", "mfcc_5",
    ]

    def __init__(self) -> None:
        self.mu:    Optional[np.ndarray] = None
        self.sigma: Optional[np.ndarray] = None
        self._fitted = False

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(self, data: np.ndarray) -> "FeatureNormalizer":
        """
        Compute μ and σ from an (N, 9) array of raw feature vectors.

        sigma is clipped to 1e-8 to handle constant features (e.g. a broken
        sensor that always reads 0°C) — this avoids division by zero.

        Args:
            data: (N, 9) float32 array from packet_to_raw_features()
        Returns:
            self (for chaining)
        """
        assert data.ndim == 2 and data.shape[1] == self.N_FEATURES, (
            f"Expected (N, {self.N_FEATURES}), got {data.shape}"
        )
        self.mu    = data.mean(axis=0).astype(np.float32)
        self.sigma = np.clip(data.std(axis=0), 1e-8, None).astype(np.float32)
        self._fitted = True

        for name, mu, sigma in zip(self.FEATURE_NAMES, self.mu, self.sigma):
            logger.debug("  %-15s  μ=%+8.3f  σ=%8.3f", name, mu, sigma)
        return self

    # ── Transform ─────────────────────────────────────────────────────────────

    def transform(self, x: np.ndarray) -> np.ndarray:
        """
        Apply z-score: (x − μ) / σ.
        x can be (9,) for a single sample or (N, 9) for a batch.
        Output dtype is float32.
        """
        self._require_fitted()
        return ((x - self.mu) / self.sigma).astype(np.float32)

    def inverse_transform(self, x: np.ndarray) -> np.ndarray:
        """Reverse: x * σ + μ. Useful for debugging and visualisation."""
        self._require_fitted()
        return (x * self.sigma + self.mu).astype(np.float32)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Write μ and σ to a JSON file (human-readable for auditing)."""
        self._require_fitted()
        Path(path).write_text(json.dumps(
            {"mu": self.mu.tolist(), "sigma": self.sigma.tolist()},
            indent=2,
        ))
        logger.info("Normalizer saved → %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "FeatureNormalizer":
        """Load μ and σ from a JSON file produced by save()."""
        d = json.loads(Path(path).read_text())
        norm = cls()
        norm.mu    = np.array(d["mu"],    dtype=np.float32)
        norm.sigma = np.array(d["sigma"], dtype=np.float32)
        norm._fitted = True
        return norm

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("FeatureNormalizer not fitted. Call fit() first.")


# ── Datasets ─────────────────────────────────────────────────────────────────

def _build_raw_arrays(df) -> Tuple[np.ndarray, np.ndarray]:
    """
    Internal helper: build raw (un-normalised) feature matrices from a DataFrame.
    Returns (raw_in, raw_out), each shape (N, 9).
    """
    mfcc_in_cols  = [f"mfcc_in_{i}"  for i in range(1, 6)]
    mfcc_out_cols = [f"mfcc_out_{i}" for i in range(1, 6)]

    rms_in  = np.log(np.maximum(df["rms_in"].values,  1e-12))
    rms_out = np.log(np.maximum(df["rms_out"].values, 1e-12))

    raw_in = np.column_stack([
        df["t_in_C"].values,
        df["h_in_pct"].values,
        rms_in,
        df["dom_freq_in_hz"].values,
        df[mfcc_in_cols].values,
    ]).astype(np.float32)

    raw_out = np.column_stack([
        df["t_out_C"].values,
        df["h_out_pct"].values,
        rms_out,
        df["dom_freq_out_hz"].values,
        df[mfcc_out_cols].values,
    ]).astype(np.float32)

    return raw_in, raw_out


class BeehiveDataset(Dataset):
    """
    Unlabelled dataset for CMC pre-training (Phase 1).

    Each item is a (x_in, x_out) pair from the SAME timestamp.
    The pairing itself IS the supervision signal — no class labels needed.

    Expected CSV columns:
        t_in_C, t_out_C, h_in_pct, h_out_pct,
        rms_in, rms_out,
        dom_freq_in_hz, dom_freq_out_hz,
        mfcc_in_1 … mfcc_in_5,
        mfcc_out_1 … mfcc_out_5,
        anomaly_flag   (optional, not used during training)

    Normalisation is applied on-the-fly in __getitem__ so the normalizer
    can be hot-swapped without rebuilding the dataset.
    """

    def __init__(
        self,
        csv_path:  str | Path,
        norm_in:   FeatureNormalizer,
        norm_out:  FeatureNormalizer,
    ) -> None:
        import pandas as pd
        df = pd.read_csv(csv_path)
        self.raw_in, self.raw_out = _build_raw_arrays(df)
        self.norm_in  = norm_in
        self.norm_out = norm_out
        logger.info("BeehiveDataset: %d unlabelled samples from %s", len(self), csv_path)

    def __len__(self) -> int:
        return len(self.raw_in)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns (x_in, x_out): both (9,) float32 tensors, z-score normalised.

        Normalisation is applied here (not in __init__) because:
        1. It avoids storing a second copy of the entire dataset.
        2. If you ever update the normalizer stats, you don't need to rebuild.
        """
        x_in  = torch.from_numpy(self.norm_in.transform(self.raw_in[idx]))
        x_out = torch.from_numpy(self.norm_out.transform(self.raw_out[idx]))
        return x_in, x_out


class LabeledBeehiveDataset(Dataset):
    """
    Labelled dataset for SupCon fine-tuning (Phase 2).

    Same CSV format as BeehiveDataset, plus a required 'label' column
    containing integer indices (0–5) matching HIVE_STATES in config.py.

    Labelling strategy (from project spec):
    ─────────────────────────────────────────
    You don't need precise start/end times. A rough window works:
        "swarm observed at 14:00" → label all packets 13:45–14:30 as class 2.
    30 events × ~10 packets each ≈ 300 samples total.
    300 labelled samples is enough for SupCon to produce well-separated clusters
    when the backbone pre-training has already found good representations.
    """

    def __init__(
        self,
        csv_path:  str | Path,
        norm_in:   FeatureNormalizer,
        norm_out:  FeatureNormalizer,
    ) -> None:
        import pandas as pd
        df = pd.read_csv(csv_path)
        assert "label" in df.columns, (
            "CSV must contain a 'label' column with integer class indices 0–5. "
            f"Valid labels: {list(enumerate(HIVE_STATES))}"
        )
        self.raw_in, self.raw_out = _build_raw_arrays(df)
        self.labels   = torch.from_numpy(df["label"].values.astype(np.int64))
        self.norm_in  = norm_in
        self.norm_out = norm_out

        # Log class distribution early — severe imbalance will hurt SupCon
        unique, counts = np.unique(df["label"].values, return_counts=True)
        dist = {HIVE_STATES[int(c)]: int(n) for c, n in zip(unique, counts)}
        logger.info("LabeledBeehiveDataset: %d samples  distribution=%s", len(self), dist)
        if min(counts) < 15:
            logger.warning(
                "Some classes have fewer than 15 samples. SupCon needs positive pairs "
                "within each batch — try to collect more labelled events."
            )

    def __len__(self) -> int:
        return len(self.raw_in)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns (x_in, x_out, label): normalised features + integer class index."""
        x_in  = torch.from_numpy(self.norm_in.transform(self.raw_in[idx]))
        x_out = torch.from_numpy(self.norm_out.transform(self.raw_out[idx]))
        return x_in, x_out, self.labels[idx]


# ── Balanced sampler ─────────────────────────────────────────────────────────

class BalancedClassSampler(Sampler):
    """
    Over/under-sample classes so every batch has a roughly equal number of
    samples from each class.

    Why this matters for SupCon:
    ─────────────────────────────
    SupCon loss requires at least 2 samples from the same class in a batch to
    form a positive pair. If a rare class appears only once in a batch, it
    contributes ZERO loss for that step — the model never learns to distinguish
    it. With a balanced sampler, each class is guaranteed to appear
    `samples_per_class` times per epoch, regardless of its true frequency.

    Minority classes are over-sampled (with replacement).
    Majority classes are under-sampled (without replacement).

    Args:
        labels:             (N,) integer class labels.
        samples_per_class:  Target samples per class per epoch.
                            A good default is min(class_counts) or 50.
    """

    def __init__(self, labels: torch.Tensor, samples_per_class: int = 50) -> None:
        self.samples_per_class = samples_per_class
        # Build a dict: class_idx → list of dataset indices
        self.indices_by_class: dict = {}
        for cls in labels.unique().tolist():
            mask = (labels == cls).nonzero(as_tuple=True)[0].tolist()
            self.indices_by_class[int(cls)] = mask

        self.n_classes = len(self.indices_by_class)

    def __iter__(self):
        all_indices = []
        for cls, idxs in self.indices_by_class.items():
            # replace=True if the class has fewer samples than the target
            # replace=False if it has more (random sub-sampling)
            replace = len(idxs) < self.samples_per_class
            chosen  = np.random.choice(idxs, size=self.samples_per_class, replace=replace)
            all_indices.extend(chosen.tolist())

        np.random.shuffle(all_indices)
        return iter(all_indices)

    def __len__(self) -> int:
        return self.samples_per_class * self.n_classes
