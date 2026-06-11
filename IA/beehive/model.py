"""
beehive/model.py
─────────────────────────────────────────────────────────────────────────────
All model components.  Import summary:

    BeehiveEncoder          MLP: (B,9) → (B,32)          ← default, use this
    BeehiveCNNEncoder       CNN: (B,1,13,T) → (B,32)     ← optional, WiFi-only
    ProjectionHead          Linear + L2-norm: (B,32)→(B,16)
    ContrastiveBeehiveModel Two encoders + two proj heads (pre-training)
    ClassifierHead          MLP: (B,64) → (B,6)          ← fine-tuning/inference
    BeehiveFineTuner        Frozen backbone + trainable classifier

Architecture flow
─────────────────
                   ┌─── encoder_in (MLP) ──── proj_in ───→  z_in  (16-d, unit sphere)
  x_in  (9-d) ────┤
                   └─────────────────────────────────────→  h_in  (32-d, backbone)

                   ┌─── encoder_out (MLP) ─── proj_out ──→  z_out (16-d, unit sphere)
  x_out (9-d) ────┤
                   └─────────────────────────────────────→  h_out (32-d, backbone)

  During pre-training:  InfoNCELoss(z_in, z_out)
  During fine-tuning:   ClassifierHead(h_in, h_out) → logits (6-d)
  During inference:     softmax(logits) → probabilities (6-d)

Why two encoders instead of one shared encoder?
────────────────────────────────────────────────
The inside and outside sensors live in systematically different environments:
  - Inside : ~34°C, high humidity, constant bee hum, queen/brood sounds
  - Outside: variable ambient T°, weather noise, flight and guard sounds
If we shared weights, the encoder would average these two distributions and
produce weaker representations for both. Separate weights let each encoder
specialise. The contrastive loss then ALIGNS the two learned spaces —
meaning same-state embeddings end up close — without forcing shared parameters.
"""

from __future__ import annotations
import torch
import torch.nn as nn
import torch.nn.functional as F
from .config import ModelConfig, NUM_CLASSES, MODEL_CFG


# ─── MLP Encoder (primary architecture) ──────────────────────────────────────

class BeehiveEncoder(nn.Module):
    """
    Two-layer MLP encoder that maps a 9-d normalised feature vector to a
    32-d embedding (the "backbone" representation used at inference).

    Architecture:
        Linear(9 → 64) → BatchNorm1d(64) → ReLU
        Linear(64 → 32) → BatchNorm1d(32) → ReLU

    BatchNorm placement (before ReLU, not after):
    ──────────────────────────────────────────────
    Placing BN before ReLU keeps activations centred around 0 before the
    non-linearity clips negative values. This reduces the "dying ReLU"
    problem where neurons become permanently inactive and produces slightly
    more stable gradients in practice for small tabular datasets like ours.

    Note: BatchNorm1d requires B ≥ 2 at training time (can't compute batch
    statistics from a single sample). At inference, BN uses running statistics
    accumulated during training, so single-sample inference is fine — but
    you MUST call model.eval() first to switch BatchNorm to running-stats mode.
    """

    def __init__(
        self,
        input_dim:  int = MODEL_CFG.input_dim,   # 9
        hidden_dim: int = MODEL_CFG.hidden_dim,   # 64
        embed_dim:  int = MODEL_CFG.embed_dim,    # 32
    ) -> None:
        super().__init__()
        self.embed_dim = embed_dim

        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),

            nn.Linear(hidden_dim, embed_dim),
            nn.BatchNorm1d(embed_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, input_dim) batch of z-score normalised feature vectors
        Returns:
            (B, embed_dim) backbone embeddings — NOT L2-normalised
        """
        return self.net(x)


# ─── CNN Encoder (optional, for richer MFCC input over WiFi) ─────────────────

class BeehiveCNNEncoder(nn.Module):
    """
    Optional CNN encoder for use if you switch from LoRa to WiFi and can
    afford to transmit the full MFCC matrix instead of just 5 coefficients.

    Input:  (B, 1, n_mfcc, T) — a "spectrogram image" with one channel.
    Output: (B, embed_dim)    — same as BeehiveEncoder, plug-in compatible.

    Example usage:
        # 4 seconds × 31.25 frames/sec ≈ 125 frames; 13 MFCC coefficients
        x = torch.randn(32, 1, 13, 125)   # (B, C, freq, time)
        encoder = BeehiveCNNEncoder(n_mfcc=13, embed_dim=32)
        h = encoder(x)   # (32, 32)

    Why Conv2d instead of Conv1d?
    ──────────────────────────────
    The MFCC matrix is 2-dimensional: frequency (13 rows) × time (T columns).
    Conv2d with a (3×5) kernel captures both spectral shape (3 rows) and
    short-time patterns (5 columns ≈ 160 ms at 31 fps). Conv1d along the time
    axis would ignore cross-MFCC correlations.

    This encoder is NOT used by default because:
    1. The LoRa payload only carries 5 MFCC coefficients, not the full matrix.
    2. The 9-d MLP encoder is simpler to debug and faster to train.
    To use this encoder, pass it to ContrastiveBeehiveModel as encoder_class.
    """

    def __init__(
        self,
        n_mfcc:    int = 13,
        embed_dim: int = MODEL_CFG.embed_dim,  # 32
    ) -> None:
        super().__init__()
        self.embed_dim = embed_dim

        # Two conv blocks, each halving the time dimension
        self.conv = nn.Sequential(
            # Block 1: (B, 1, 13, T) → (B, 32, 11, T//2)
            nn.Conv2d(1, 32, kernel_size=(3, 5), padding=(1, 2)),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(1, 2)),       # halve time, keep freq

            # Block 2: (B, 32, 11, T//2) → (B, 64, 9, T//4)
            nn.Conv2d(32, 64, kernel_size=(3, 3), padding=(1, 1)),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),            # global average → (B, 64, 1, 1)
        )
        self.fc = nn.Sequential(
            nn.Flatten(),                            # (B, 64)
            nn.Linear(64, embed_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 1, n_mfcc, T) — raw MFCC matrix with 1 channel
        Returns:
            (B, embed_dim)
        """
        return self.fc(self.conv(x))


# ─── Projection head ─────────────────────────────────────────────────────────

class ProjectionHead(nn.Module):
    """
    Single linear layer followed by L2 normalisation.
    Used only DURING contrastive pre-training; discarded at inference.

    Why a separate head instead of normalising the encoder output?
    ──────────────────────────────────────────────────────────────
    The backbone (32-d) feeds both the contrastive loss AND the classifier.
    Forcing the backbone onto a unit sphere would remove magnitude information
    that the classifier relies on (e.g., very loud = high RMS feature value).
    The projection head absorbs all the sphere-compression, leaving the
    backbone free to retain magnitude information.

    Why no bias in the linear layer?
    ─────────────────────────────────
    L2 normalisation makes bias redundant: a constant offset is divided away
    by the norm. Removing it saves 16 parameters and slightly speeds training.
    """

    def __init__(
        self,
        input_dim: int = MODEL_CFG.embed_dim,  # 32
        proj_dim:  int = MODEL_CFG.proj_dim,   # 16
    ) -> None:
        super().__init__()
        self.linear = nn.Linear(input_dim, proj_dim, bias=False)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        """
        Args:
            h: (B, input_dim) backbone embedding
        Returns:
            (B, proj_dim) L2-normalised — each row has unit norm.
            Dot product of any two rows == their cosine similarity.
        """
        return F.normalize(self.linear(h), dim=-1)


# ─── Contrastive model (two encoders + two projection heads) ─────────────────

class ContrastiveBeehiveModel(nn.Module):
    """
    Full contrastive model for Phase 1 pre-training.
    Wraps two independent (encoder, projection_head) pairs.

    Input:  x_in (B,9), x_out (B,9) — normalised feature vectors
    Output: h_in, h_out (B,32) backbone; z_in, z_out (B,16) projections

    The InfoNCE loss is computed on z_in / z_out during training.
    At inference, only h_in / h_out are used (passed to ClassifierHead).

    This design matches CMC (Contrastive Multiview Coding): the two sensor
    streams are treated as two "views" of the same underlying hive state.
    Positive pairs = (inside at t, outside at t).
    Negatives = all cross-sensor pairs within the batch from different times.
    """

    def __init__(self, cfg: ModelConfig = MODEL_CFG) -> None:
        super().__init__()
        self.cfg = cfg

        # Two INDEPENDENT encoders — do NOT share weights (see module docstring)
        self.encoder_in  = BeehiveEncoder(cfg.input_dim, cfg.hidden_dim, cfg.embed_dim)
        self.encoder_out = BeehiveEncoder(cfg.input_dim, cfg.hidden_dim, cfg.embed_dim)

        # Two INDEPENDENT projection heads
        self.proj_in  = ProjectionHead(cfg.embed_dim, cfg.proj_dim)
        self.proj_out = ProjectionHead(cfg.embed_dim, cfg.proj_dim)

    def forward(
        self,
        x_in:  torch.Tensor,  # (B, 9)
        x_out: torch.Tensor,  # (B, 9)
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns:
            h_in  (B, 32): backbone embedding, inside  — used at inference
            h_out (B, 32): backbone embedding, outside — used at inference
            z_in  (B, 16): L2-norm projection, inside  — used during training
            z_out (B, 16): L2-norm projection, outside — used during training
        """
        h_in  = self.encoder_in(x_in)
        h_out = self.encoder_out(x_out)
        z_in  = self.proj_in(h_in)
        z_out = self.proj_out(h_out)
        return h_in, h_out, z_in, z_out

    def encode(
        self,
        x_in:  torch.Tensor,
        x_out: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Inference-only shortcut: skips the projection heads entirely.
        Slightly faster and avoids calling proj_in/proj_out unnecessarily.

        Always call model.eval() before inference to switch BatchNorm from
        batch-statistics mode to running-statistics mode.
        """
        return self.encoder_in(x_in), self.encoder_out(x_out)


# ─── Classifier head ─────────────────────────────────────────────────────────

class ClassifierHead(nn.Module):
    """
    Two-layer MLP that maps concatenated backbone embeddings → class logits.

    Input:  concat(h_in, h_out) ∈ ℝ^64   (both 32-d backbone outputs)
    Hidden: Linear(64→32) → ReLU → Dropout
    Output: Linear(32→6) raw logits       (apply softmax for probabilities)

    Why concatenate h_in and h_out instead of adding/averaging?
    ────────────────────────────────────────────────────────────
    Adding or averaging h_in and h_out destroys the directional relationship
    between the two sensors. Many hive states are only distinguishable by
    their ASYMMETRY:
      - Swarming  : outside RMS↑ + outside freq↑ + inside normal
      - Queenless : inside freq unstable + inside T° variable + outside normal
      - Attack    : both channels spike simultaneously
    Concatenation lets the MLP learn these asymmetric interaction patterns.

    Why NOT update the backbone during fine-tuning?
    ─────────────────────────────────────────────────
    With only 30–50 events per class, unfreezing the full backbone (≈ 5,000
    parameters) would overfit in a few dozen steps. The classifier head has
    only 32×64 + 6×32 = 2,240 parameters — safe to train from sparse labels.
    The backbone can optionally be unfrozen at a very low lr (1e-5) for a
    final 10-epoch refinement pass once the classifier has stabilised.
    """

    def __init__(
        self,
        embed_dim:   int = MODEL_CFG.embed_dim,   # 32 per sensor
        hidden_dim:  int = 32,
        num_classes: int = NUM_CLASSES,           # 6
        dropout:     float = 0.3,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(2 * embed_dim, hidden_dim),  # 64 → 32
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes),    # 32 → 6
            # No softmax here — CrossEntropyLoss and SupConLoss expect raw logits.
            # Call F.softmax(logits, dim=-1) only when you need actual probabilities.
        )

    def forward(self, h_in: torch.Tensor, h_out: torch.Tensor) -> torch.Tensor:
        """
        Args:
            h_in:  (B, 32) inside backbone embedding
            h_out: (B, 32) outside backbone embedding
        Returns:
            (B, 6) raw logits (unnormalised scores per class)
        """
        x = torch.cat([h_in, h_out], dim=-1)  # (B, 64)
        return self.net(x)


# ─── Fine-tuner (frozen backbone + trainable classifier) ─────────────────────

class BeehiveFineTuner(nn.Module):
    """
    Combines a pre-trained ContrastiveBeehiveModel (frozen) with a fresh
    ClassifierHead for Phase 2 fine-tuning.

    The backbone is frozen immediately on construction by setting
    requires_grad=False on all its parameters. The optimiser passed in
    train.py ONLY receives classifier.parameters(), so gradient updates
    are strictly limited to the 2,240-parameter head.

    Usage:
        finetuner = BeehiveFineTuner(pretrained_model)
        opt = Adam(finetuner.classifier.parameters(), lr=1e-3)
        # ... training loop ...
        # Optional: unfreeze for end-to-end refinement
        finetuner.unfreeze_backbone()
        opt_e2e = Adam(finetuner.parameters(), lr=1e-5)
    """

    def __init__(
        self,
        backbone:   ContrastiveBeehiveModel,
        classifier: ClassifierHead | None = None,
    ) -> None:
        super().__init__()
        self.backbone   = backbone
        self.classifier = classifier or ClassifierHead(embed_dim=backbone.cfg.embed_dim)
        self._freeze_backbone()

    def _freeze_backbone(self) -> None:
        """Freeze all backbone parameters (encoders + projection heads)."""
        for p in self.backbone.parameters():
            p.requires_grad = False

    def unfreeze_backbone(self) -> None:
        """
        Unfreeze the backbone for end-to-end fine-tuning.
        Use a very small learning rate (1e-5) to avoid catastrophic forgetting
        of the contrastive representations learned in Phase 1.
        """
        for p in self.backbone.parameters():
            p.requires_grad = True

    def forward(self, x_in: torch.Tensor, x_out: torch.Tensor) -> torch.Tensor:
        """
        Returns raw logits (B, 6).

        Implementation note: requires_grad=False on backbone parameters is
        sufficient to stop gradient flow through them. We do NOT wrap with
        torch.no_grad() because that would also block gradients for the
        classifier, which is what we're trying to train.
        """
        h_in, h_out = self.backbone.encode(x_in, x_out)
        return self.classifier(h_in, h_out)

    @property
    def n_trainable(self) -> int:
        """Number of trainable parameters (should be ~2,240 while backbone is frozen)."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @property
    def n_total(self) -> int:
        return sum(p.numel() for p in self.parameters())
