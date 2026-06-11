"""
beehive/losses.py
─────────────────────────────────────────────────────────────────────────────
Two contrastive losses for the two training phases.

Phase 1 (no labels)  →  InfoNCELoss    (CMC / CLIP-style)
Phase 2 (few labels) →  SupConLoss     (Supervised Contrastive)

Both losses work on L2-normalised embeddings, so dot product == cosine similarity.
Both are divided by a temperature τ that controls how "sharp" the distribution is.

Maths refresher — why these losses work
─────────────────────────────────────────
After training, the embedding space organises itself so that:
  • Packets from the same hive state are nearby (high cosine similarity).
  • Packets from different hive states are far apart (low cosine similarity).

Neither loss sees raw audio or labels (in Phase 1). They only see a rule:
"these two embeddings SHOULD be close; all others SHOULD be far."
The encoder then learns to produce embeddings that satisfy that rule —
and in doing so, it inevitably learns what makes hive states different.
"""

from __future__ import annotations
import torch
import torch.nn as nn
import torch.nn.functional as F


# ─── Phase 1: InfoNCE ────────────────────────────────────────────────────────

class InfoNCELoss(nn.Module):
    """
    Information Noise Contrastive Estimation for pre-training.

    Positive pair:  (z_in[i], z_out[i]) — same timestamp, same hive state
    Negatives:      (z_in[i], z_out[j]) for all j ≠ i within the batch

    Formula (one direction):
        L_i = −log ──────────────────────────────────────────────────────
                    exp(z_in[i]·z_out[i] / τ)
                   ───────────────────────────────────────────────────────
                    Σ_{j=0}^{B-1}  exp(z_in[i]·z_out[j] / τ)

    Intuition: for each inside embedding z_in[i], the model must identify
    the correct outside embedding z_out[i] from a "line-up" of B candidates.
    As B grows, the task gets harder — which is why large batch sizes improve
    contrastive learning (more negatives = harder negatives = better gradients).

    The loss is computed SYMMETRICALLY (in→out AND out→in) and averaged.
    Without symmetry, one encoder can collapse to a trivial constant vector
    while the other encodes everything — the loss would be minimised but the
    representations would be useless.

    Temperature τ intuition:
    ─────────────────────────
    τ controls how "focused" the softmax distribution is:
      τ = 0.07: very peaked, pushes hard on the closest negatives
      τ = 0.20: smooth distribution, gentle gradients
    Start with τ = 0.07. If training is unstable (loss spikes or NaN),
    increase to 0.10. If the model converges too slowly, try 0.05.
    Never go below 0.03 — exp() can overflow with many elements in the sum.
    """

    def __init__(self, temperature: float = 0.07) -> None:
        super().__init__()
        if temperature < 0.03:
            raise ValueError(f"τ={temperature} is dangerously small; use ≥ 0.03")
        self.tau = temperature

    def forward(
        self,
        z_in:  torch.Tensor,  # (B, D) — L2-normalised inside projections
        z_out: torch.Tensor,  # (B, D) — L2-normalised outside projections
    ) -> torch.Tensor:
        """
        Computes symmetric InfoNCE loss.

        Returns: scalar loss value.
        """
        B = z_in.shape[0]
        if B < 2:
            raise ValueError("Batch size must be ≥ 2 for contrastive learning")

        # ── Step 1: All-pairs cosine similarity matrix ─────────────────────
        # Because z_in and z_out are L2-normalised:
        #   torch.mm(z_in, z_out.T)[i,j] = dot(z_in[i], z_out[j])
        #                                = cosine_similarity(z_in[i], z_out[j])
        # Dividing by τ sharpens the distribution (smaller τ = sharper).
        # Shape: (B, B), where [i,j] is the similarity of pair (z_in[i], z_out[j])
        logits = torch.mm(z_in, z_out.T) / self.tau

        # ── Step 2: Labels — the diagonal is always the positive pair ──────
        # logits[i,i] = similarity of (z_in[i], z_out[i]) = the positive pair.
        # This turns the problem into a B-way classification per row:
        # "which column j is the correct match for z_in[i]? Answer: j=i."
        labels = torch.arange(B, device=z_in.device)

        # ── Step 3: Cross-entropy in both directions ────────────────────────
        # F.cross_entropy(logits, labels) is exactly:
        #   Σ_i  −log( exp(logits[i,i]) / Σ_j exp(logits[i,j]) )
        # which IS the InfoNCE formula shown in the docstring.
        # The transpose handles the reverse direction (z_out[i] → find z_in[i]).
        loss_i2o = F.cross_entropy(logits,   labels)   # inside  → outside
        loss_o2i = F.cross_entropy(logits.T, labels)   # outside → inside
        return (loss_i2o + loss_o2i) / 2.0

    @torch.no_grad()
    def top1_retrieval(self, z_in: torch.Tensor, z_out: torch.Tensor) -> float:
        """
        Top-1 retrieval accuracy: for each z_in[i], is z_out[i] the nearest
        neighbour among all z_out in the batch?

        This is a fast, interpretable training diagnostic:
          - Epoch 1:   ~1/B (random, e.g. 1.6% for B=64)
          - Epoch 50:  typically 20–40%
          - Epoch 100: typically 60–80%
          - Epoch 200: typically 80–95% (if data quality is good)

        Values below 30% after epoch 100 indicate one of:
          1. Too few samples — more data needed
          2. τ too large — try reducing to 0.07
          3. Features are not discriminative enough for this hive
        """
        logits = torch.mm(z_in, z_out.T)          # no τ for retrieval
        preds  = logits.argmax(dim=1)
        labels = torch.arange(B := z_in.shape[0], device=z_in.device)
        return (preds == labels).float().mean().item()


# ─── Phase 2: Supervised Contrastive (SupCon) ────────────────────────────────

class SupConLoss(nn.Module):
    """
    Supervised Contrastive Loss for fine-tuning.
    Reference: Khosla et al. "Supervised Contrastive Learning" NeurIPS 2020.

    Key difference from InfoNCE:
    ─────────────────────────────
      InfoNCE: positives are fixed — always the paired sensor (same timestamp).
      SupCon:  positives are all samples with the SAME CLASS LABEL in the batch.

    So a "pre_swarming" packet from Monday and one from Thursday become a
    positive pair — the model is pushed to make ALL pre-swarming embeddings
    similar to each other, regardless of which specific day or time they came from.
    This forces the encoder to learn a truly class-level invariance.

    Formula for anchor i:
        L_i = -1/|P(i)| × Σ_{p ∈ P(i)} log exp(s_ip / τ) / Σ_{a≠i} exp(s_ia / τ)

    where P(i) = {all j where label[j] == label[i] and j ≠ i}
    and   s_ij = cosine_similarity(emb[i], emb[j])

    The denominator sums over ALL other samples (both positive and negative).
    This is the standard SupCon formulation — it's more conservative than
    summing only over negatives (which would be NT-Xent / SimCLR style).

    CRITICAL: batch construction matters
    ──────────────────────────────────────
    If a class appears only ONCE in a batch, |P(i)| = 0 for that sample.
    There are no positive pairs, so that sample contributes ZERO loss.
    The model never learns to separate that class. This is why you MUST use
    BalancedClassSampler (see data.py) to ensure each class appears ≥ 4 times
    per batch. With samples_per_class=50 and B=64, most batches will have
    8+ samples per class.
    """

    def __init__(self, temperature: float = 0.07) -> None:
        super().__init__()
        self.tau = temperature

    def forward(
        self,
        embeddings: torch.Tensor,  # (B, D) — L2-normalised
        labels:     torch.Tensor,  # (B,)   — integer class indices
    ) -> torch.Tensor:
        """
        Args:
            embeddings: (B, D) L2-normalised embeddings.
                        Pass the BACKBONE outputs (h_in / h_out), not projections.
                        L2-normalise them here before passing:
                        e.g. F.normalize(torch.cat([h_in, h_out], dim=-1), dim=-1)
            labels:     (B,) integer class indices on the same device.

        Returns:
            Scalar loss value.
        """
        B      = embeddings.shape[0]
        device = embeddings.device

        # ── Step 1: Pairwise cosine similarities ───────────────────────────
        # sim_matrix[i,j] = cos_sim(emb[i], emb[j]) / τ
        # Shape: (B, B)
        sim = torch.mm(embeddings, embeddings.T) / self.tau

        # ── Step 2: Mask out the diagonal (self-comparison) ────────────────
        # An anchor is never its own positive.
        # Self-similarity is always 1.0 (after L2 norm), which would dominate
        # the numerator and prevent any meaningful learning.
        diag_mask = torch.eye(B, dtype=torch.bool, device=device)
        sim = sim.masked_fill(diag_mask, -1e9)   # effectively exp(-1e9/τ) ≈ 0

        # ── Step 3: Positive mask ──────────────────────────────────────────
        # pos_mask[i,j] = True  iff  labels[i] == labels[j]  AND  i ≠ j
        #
        # Broadcasting trick: labels[:, None] has shape (B, 1)
        #                      labels[None, :] has shape (1, B)
        # Their equality comparison broadcasts to (B, B)
        pos_mask = (labels[:, None] == labels[None, :]) & ~diag_mask  # (B, B)

        # ── Step 4: Log-softmax denominator ───────────────────────────────
        # For each anchor i, the denominator is Σ_{a≠i} exp(sim[i,a]).
        # Using logsumexp for numerical stability:
        #   logsumexp(sim[i]) = log Σ_a exp(sim[i,a])
        # The diagonal is already masked to -1e9 so it contributes ~0.
        log_denom = torch.logsumexp(sim, dim=1, keepdim=True)   # (B, 1)

        # ── Step 5: Log-probability for each pair ─────────────────────────
        # log_prob[i,j] = log( exp(sim[i,j]) / Σ_{a≠i} exp(sim[i,a]) )
        #               = sim[i,j] - log_denom[i]
        log_prob = sim - log_denom   # (B, B)

        # ── Step 6: Mean over positive pairs per anchor ───────────────────
        # For anchor i:  loss_i = -1/|P(i)| × Σ_{p ∈ P(i)} log_prob[i,p]
        n_pos = pos_mask.sum(dim=1).float()   # (B,) — count of positives per anchor

        # Skip anchors with NO positives in this batch.
        # This happens when a class appears only once; rather than NaN-ing
        # the gradient, we skip those anchors and warn.
        valid = n_pos > 0
        if not valid.any():
            # Entire batch has unique classes — return 0 loss with a grad.
            # This avoids NaN while still differentiating if needed.
            import warnings
            warnings.warn(
                "SupConLoss: no positive pairs in this batch. "
                "Ensure BalancedClassSampler is used and labels are correct."
            )
            return embeddings.sum() * 0.0

        # Sum log_prob over positive positions, divide by count of positives
        sum_log_prob = (pos_mask * log_prob).sum(dim=1)      # (B,)
        mean_log_prob = sum_log_prob[valid] / n_pos[valid]   # (n_valid,)

        return -mean_log_prob.mean()
