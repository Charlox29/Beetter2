"""
beehive/config.py
─────────────────────────────────────────────────────────────────────────────
Single source of truth for all hyperparameters.

Keeping everything here means you only change numbers in one file when tuning,
rather than hunting through pretrain.py, losses.py, and inference.py separately.
"""

from dataclasses import dataclass, field
from typing import List

# ── Hive states ───────────────────────────────────────────────────────────────
# The index of each string IS the class label the classifier outputs.
# Changing this order would break any saved model — add new classes at the end.
HIVE_STATES: List[str] = [
    "normal",            # 0  stable hum 200–400 Hz, inside T° ~34°C
    "pre_swarming",      # 1  rising 350–500 Hz, inside T° climbing, 2–4 h before swarm
    "swarming",          # 2  ~500 Hz spike, outside audio surges as bees leave
    "queen_competition", # 3  tooting (350–500 Hz sweep) + quacking (200–350 Hz constant)
    "queenless",         # 4  ~350 Hz, long-term T° instability
    "attack",            # 5  500–700 Hz sudden spike, guard bee piping
]
NUM_CLASSES = len(HIVE_STATES)   # 6


@dataclass
class ModelConfig:
    """
    Encoder + projection head dimensions.

    The hierarchy is: raw sensor (9-d) → encoder backbone (32-d) → projection (16-d).
    ─ backbone (32-d): used at inference time, fed to the classifier
    ─ projection (16-d): used only during contrastive training, discarded afterwards

    Why the two-level design?
    The contrastive loss works best on a unit-sphere (L2-normalised space).
    Forcing the backbone onto the sphere would remove magnitude information that
    the downstream classifier finds useful (e.g., loud vs quiet hive).
    The projection head absorbs all the sphere-compression, leaving the backbone free.
    """
    input_dim:  int = 9    # T°, H%, log(RMS), dom_freq, MFCC 1-5
    hidden_dim: int = 64   # first linear layer
    embed_dim:  int = 32   # backbone output — used at inference
    proj_dim:   int = 16   # projection output — used during training only


@dataclass
class TrainConfig:
    # ── Pre-training (Phase 1, no labels needed) ─────────────────────────────
    temperature:       float = 0.07   # τ in InfoNCE; range 0.05–0.20
    # τ intuition: smaller = sharper distribution, harder negatives, more aggressive.
    # Too small (< 0.05): numerical instability (exp() overflows).
    # Too large (> 0.20): loss becomes trivially easy, model stops learning.

    pretrain_batch:    int   = 64
    pretrain_epochs:   int   = 200
    pretrain_lr:       float = 3e-4
    pretrain_wd:       float = 1e-4   # weight decay (L2 regularisation)

    # ── Fine-tuning (Phase 2, 30–50 labelled events per class) ───────────────
    finetune_batch:    int   = 64
    finetune_epochs:   int   = 100
    finetune_lr:       float = 1e-3   # higher than pretrain because only classifier trains
    supcon_weight:     float = 0.5    # λ: loss = λ·SupCon + (1-λ)·CrossEntropy
    # Setting λ=1 (pure SupCon) ignores direct class discrimination.
    # Setting λ=0 (pure CE) ignores embedding geometry.
    # 0.5 is a safe default; lower λ if your classes are very unbalanced.

    dropout:           float = 0.3    # classifier head dropout
    samples_per_class: int   = 50     # for the balanced batch sampler


@dataclass
class InferenceConfig:
    preswarm_threshold:   float = 0.40  # P(pre_swarming) must exceed this...
    alert_n_consecutive:  int   = 3     # ...for this many readings in a row to fire alert
    # At 5-minute intervals: 3 readings = 15 minutes of sustained pre-swarm signal.
    # This prevents a single noisy packet from triggering a false alarm.


@dataclass
class LoRaPacketConfig:
    """
    Schema for the 31-byte LoRa payload (little-endian).

    Original spec was 29 bytes. Two extra bytes were added for dom_freq_in and
    dom_freq_out (uint8 each, stored as Hz÷10 for 0–2550 Hz range).
    At SF9/BW125, 31 bytes ≈ 185 ms air time — still comfortably within the 1% EU
    868 MHz duty cycle even at the 30-second alert-burst interval (0.62% used).

    C equivalent (for the ESP32-C6 firmware):
        typedef struct __attribute__((packed)) {
            uint16_t timestamp;       // minutes since midnight
            int8_t   t_in, t_out;    // °C
            uint8_t  h_in, h_out;    // %
            int8_t   log_rms_in;     // log10(RMS) × 16
            int8_t   log_rms_out;
            uint8_t  dom_freq_in;    // Hz ÷ 10  (e.g. 45 → 450 Hz)
            uint8_t  dom_freq_out;
            int16_t  mfcc_in[5];     // coefficients 1–5, scaled × 10
            int16_t  mfcc_out[5];
            uint8_t  anomaly_flag;   // bitmask: bit0=RMS spike, bit1=freq>450Hz, bit2=ΔT>16°C
        } lora_payload_t;            // 31 bytes
    """
    struct_fmt: str = "<HbbBBbbBBhhhhhhhhhhB"
    size_bytes: int = 31


# ── Convenience singletons (import these everywhere instead of instantiating) ─
MODEL_CFG     = ModelConfig()
TRAIN_CFG     = TrainConfig()
INFER_CFG     = InferenceConfig()
LORA_PKT_CFG  = LoRaPacketConfig()
