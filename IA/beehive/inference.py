"""
beehive/inference.py
─────────────────────────────────────────────────────────────────────────────
Real-time inference pipeline for a single hive.

One BeehiveInference instance per hive. It is STATEFUL: it keeps a rolling
window of recent pre-swarm probabilities to implement the consecutive-readings
alert rule without re-reading from a database.

Alert logic (from project spec):
    Fire alert if:
        P(pre_swarming) > 0.40   AND
        this has been true for ≥ 3 consecutive readings

The 3-reading requirement prevents a single noisy packet from triggering
a false alarm. At 5-minute intervals, 3 readings = 15 minutes of sustained
pre-swarm signal — a biologically plausible window (real swarm prep takes
2–4 hours of rising activity).

Typical end-to-end latency for one packet:
    decode_packet()     ~0.01 ms
    feature extraction  ~0.02 ms
    normalisation       ~0.02 ms
    model forward       ~1–2 ms  (CPU, batch size 1)
    ──────────────────────────
    Total               ~2 ms    negligible vs the 5-minute packet interval
"""

from __future__ import annotations
import collections
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from .data import decode_packet, packet_to_raw_features, FeatureNormalizer
from .model import BeehiveFineTuner
from .config import InferenceConfig, HIVE_STATES, INFER_CFG

logger = logging.getLogger(__name__)


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class InferenceResult:
    """All outputs from a single packet inference pass."""
    label:                str            # e.g. "pre_swarming"
    label_idx:            int            # 0–5
    probabilities:        np.ndarray     # (6,) softmax probabilities
    alert:                bool           # True if pre-swarm alert fires
    alert_reason:         str            # human-readable explanation
    anomaly_flag:         int            # raw bitmask from LoRa packet
    consecutive_preswarm: int            # how many readings in a row above threshold
    timestamp_min:        int            # minutes since midnight from the packet

    @property
    def prob_dict(self) -> dict:
        """Returns {class_name: probability} for all 6 classes."""
        return {name: float(p) for name, p in zip(HIVE_STATES, self.probabilities)}

    def __str__(self) -> str:
        top = self.prob_dict
        bar = " · ".join(f"{k}={v:.0%}" for k, v in sorted(top.items(), key=lambda x: -x[1])[:3])
        alert_str = f"  ⚠️  ALERT: {self.alert_reason}" if self.alert else ""
        return f"[t={self.timestamp_min:04d}min] {self.label}  [{bar}]{alert_str}"


# ─── Inference engine ─────────────────────────────────────────────────────────

class BeehiveInference:
    """
    Stateful inference engine for one hive.

    Args:
        finetuner:           Trained and loaded BeehiveFineTuner. Call .eval() before
                             passing it here — or let this constructor do it.
        norm_in:             Fitted FeatureNormalizer for inside sensor.
        norm_out:            Fitted FeatureNormalizer for outside sensor.
        cfg:                 InferenceConfig with alert thresholds.
        device:              'cpu' or 'cuda'.
    """

    def __init__(
        self,
        finetuner:  BeehiveFineTuner,
        norm_in:    FeatureNormalizer,
        norm_out:   FeatureNormalizer,
        cfg:        InferenceConfig = INFER_CFG,
        device:     str = "cpu",
    ) -> None:
        self.finetuner = finetuner.to(device).eval()
        self.norm_in   = norm_in
        self.norm_out  = norm_out
        self.cfg       = cfg
        self.device    = device

        # Rolling window of pre-swarm probabilities
        # deque with maxlen automatically drops the oldest reading when full,
        # so it always represents the last `alert_n_consecutive` packets.
        self._preswarm_hist: collections.deque[float] = collections.deque(
            maxlen=cfg.alert_n_consecutive
        )
        self._preswarm_idx = HIVE_STATES.index("pre_swarming")  # = 1

    # ── Main inference entry point ────────────────────────────────────────────

    def infer(self, raw_bytes: bytes) -> InferenceResult:
        """
        Process a single raw 31-byte LoRa packet end-to-end.

        Pipeline:
            bytes → decode → raw features → normalise → tensor →
            → model forward → softmax → argmax + alert logic → InferenceResult

        Args:
            raw_bytes: 31 bytes exactly, as received from the LoRa gateway.

        Returns:
            InferenceResult with prediction, probabilities, and alert status.
        """
        # ── 1. Decode binary packet ───────────────────────────────────────
        pkt = decode_packet(raw_bytes)

        # ── 2. Extract raw (un-normalised) feature vectors ────────────────
        vec_in_raw, vec_out_raw = packet_to_raw_features(pkt)

        # ── 3. Z-score normalise ──────────────────────────────────────────
        vec_in  = self.norm_in.transform(vec_in_raw)    # (9,) float32
        vec_out = self.norm_out.transform(vec_out_raw)  # (9,) float32

        # ── 4. Tensor with batch dimension ────────────────────────────────
        x_in  = torch.from_numpy(vec_in).unsqueeze(0).to(self.device)   # (1, 9)
        x_out = torch.from_numpy(vec_out).unsqueeze(0).to(self.device)  # (1, 9)

        # ── 5. Model forward pass ─────────────────────────────────────────
        # torch.no_grad() is used here (unlike in train.py) because at
        # inference we never call .backward(). no_grad() disables the
        # autograd engine entirely, reducing memory usage and speeding up
        # the forward pass by ~20% on CPU.
        with torch.no_grad():
            logits = self.finetuner(x_in, x_out)    # (1, 6) raw logits
            probs  = F.softmax(logits, dim=-1)       # (1, 6) probabilities
            probs_np = probs.squeeze(0).cpu().numpy()  # (6,)

        # ── 6. Argmax prediction ──────────────────────────────────────────
        label_idx = int(probs_np.argmax())
        label     = HIVE_STATES[label_idx]

        # ── 7. Alert logic ────────────────────────────────────────────────
        preswarm_p = float(probs_np[self._preswarm_idx])
        self._preswarm_hist.append(preswarm_p)

        alert        = False
        alert_reason = ""

        # Count how many of the last N readings exceeded the threshold.
        # We require the FULL window to be filled (len == maxlen) before
        # firing — this prevents an alert on the very first reading.
        n_above = sum(p > self.cfg.preswarm_threshold for p in self._preswarm_hist)
        n_hist  = len(self._preswarm_hist)

        if n_hist == self.cfg.alert_n_consecutive and n_above == n_hist:
            alert = True
            alert_reason = (
                f"P(pre_swarming) > {self.cfg.preswarm_threshold:.0%} for "
                f"{self.cfg.alert_n_consecutive} consecutive readings "
                f"(current: {preswarm_p:.1%})"
            )
            logger.warning("SWARM ALERT fired: %s", alert_reason)

        return InferenceResult(
            label=label,
            label_idx=label_idx,
            probabilities=probs_np,
            alert=alert,
            alert_reason=alert_reason,
            anomaly_flag=pkt["anomaly_flag"],
            consecutive_preswarm=n_above,
            timestamp_min=pkt["timestamp_min"],
        )

    # ── Utility methods ───────────────────────────────────────────────────────

    def reset_alert(self) -> None:
        """
        Clear the rolling pre-swarm history.
        Call this after a confirmed swarm (e.g., the beekeeper split the colony)
        to prevent spurious follow-up alerts from the history window.
        """
        self._preswarm_hist.clear()
        logger.info("Alert history reset.")

    def infer_batch(self, raw_packets: list[bytes]) -> list[InferenceResult]:
        """
        Process a list of packets in chronological order.

        Note: This still calls infer() one-at-a-time to correctly update
        the rolling alert history. Batching the model forward pass is a possible
        optimisation if latency ever becomes a concern.
        """
        return [self.infer(pkt) for pkt in raw_packets]

    @property
    def recent_preswarm_probs(self) -> list[float]:
        """The last N pre-swarm probabilities seen (oldest first)."""
        return list(self._preswarm_hist)


# ─── Quick sanity check ──────────────────────────────────────────────────────

def run_smoke_test(model_path: str, norm_in_path: str, norm_out_path: str) -> None:
    """
    Build a BeehiveInference from saved files and run one synthetic packet through
    it. Useful as a deployment sanity check.

    >>> run_smoke_test("checkpoints/finetune_best.pt",
    ...                "calibration/norm_in.json",
    ...                "calibration/norm_out.json")
    """
    import struct

    from .model import ContrastiveBeehiveModel, BeehiveFineTuner
    from .config import MODEL_CFG, LORA_PKT_CFG

    # Build and load model
    backbone   = ContrastiveBeehiveModel(MODEL_CFG)
    finetuner  = BeehiveFineTuner(backbone)
    state = torch.load(model_path, map_location="cpu", weights_only=True)
    finetuner.load_state_dict(state)

    # Load normalizers
    norm_in  = FeatureNormalizer.load(norm_in_path)
    norm_out = FeatureNormalizer.load(norm_out_path)

    engine = BeehiveInference(finetuner, norm_in, norm_out)

    # Synthetic packet: typical inside-hive readings (normal state)
    # timestamp=480 (8am), T_in=34, T_out=18, H_in=65, H_out=50,
    # log_rms_in=-32 (→ 10^(-2)=0.01), dom_freq_in=30 (→300Hz),
    # mfcc_in=[−50,20,−10,5,−3] (all ×10), same for out, flag=0
    fmt = LORA_PKT_CFG.struct_fmt
    raw = struct.pack(
        fmt,
        480,                    # timestamp minutes
        34, 18,                 # T_in, T_out
        65, 50,                 # H_in, H_out
        -32, -48,               # log_rms_in (0.01), log_rms_out (0.001)
        30, 25,                 # dom_freq_in (300Hz), dom_freq_out (250Hz)
        -50, 20, -10, 5, -3,   # mfcc_in ×10
        -45, 18,  -8, 4, -2,   # mfcc_out ×10
        0,                      # anomaly_flag
    )

    result = engine.infer(raw)
    print(result)
    print(f"Smoke test passed. Prediction: {result.label}")
