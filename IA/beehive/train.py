"""
beehive/train.py
─────────────────────────────────────────────────────────────────────────────
Two-phase training pipeline.

  pretrain(model, dataset, ...)
    Phase 1: CMC contrastive pre-training on unlabelled data.
    Loss: InfoNCELoss. No labels needed.
    Duration: ~200 epochs. Stop when retrieval accuracy plateaus.

  finetune(backbone, dataset, ...)
    Phase 2: SupCon + CrossEntropy on labelled hive events.
    The backbone is frozen; only the ClassifierHead trains.
    Duration: ~100 epochs.

Expected t-SNE timeline (run visualize.py every 10 epochs to check):
  Epoch 10:  scattered random cloud (expected — backbone is random)
  Epoch 50:  vague clusters starting to form
  Epoch 100: distinct clusters visible for most hive states
  Epoch 200: tight, well-separated clusters (swarming, queenless, etc.)

If clusters don't form by epoch 100, check:
  1. Batch size: increase to 128 or 256 (more negatives = better signal)
  2. Temperature τ: try 0.10 if training is unstable, 0.05 if too slow
  3. Data quality: are inside/outside pairs truly from the same timestamp?
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

from .model import ContrastiveBeehiveModel, BeehiveFineTuner, ClassifierHead
from .losses import InfoNCELoss, SupConLoss
from .data import BeehiveDataset, LabeledBeehiveDataset, BalancedClassSampler
from .config import TrainConfig, TRAIN_CFG, HIVE_STATES

logger = logging.getLogger(__name__)


# ─── Phase 1: Pre-training ────────────────────────────────────────────────────

def pretrain(
    model:           ContrastiveBeehiveModel,
    dataset:         BeehiveDataset,
    *,
    cfg:             TrainConfig  = TRAIN_CFG,
    device:          str          = "cpu",
    checkpoint_dir:  Optional[Path] = None,
    log_every:       int          = 10,
) -> ContrastiveBeehiveModel:
    """
    Pre-train the contrastive model on unlabelled (x_in, x_out) pairs.

    What is learned:
    ─────────────────
    The ONLY supervision: "the inside and outside readings at the SAME moment
    in time should be nearby in embedding space."
    The model has no idea what 'swarming' or 'queenless' means. It just learns
    that if two sensors agreed at time T (same hive state), their embeddings
    should agree too. Over 200 epochs, this forces the model to find the
    underlying structure that makes sensor readings self-consistent — which
    ends up being the hive state.

    Learning rate schedule:
    ────────────────────────
    CosineAnnealingLR decays lr from `pretrain_lr` to ~0 over the full run.
    This provides large, exploratory steps early (when embeddings are random)
    and fine-grained steps later (when clusters are almost formed).
    A fixed lr typically causes the loss to plateau around epoch 50 and then
    barely improve — the scheduler is important.

    Gradient clipping:
    ───────────────────
    Clips the global norm of all gradients to 1.0 before each update.
    Prevents the occasional very large gradient (from hard negative pairs
    early in training) from catastrophically updating the weights.
    """
    model = model.to(device)

    # drop_last=True: partial batches at epoch end have fewer negatives,
    # which inflates the loss. Drop them for consistent training signal.
    loader = DataLoader(
        dataset,
        batch_size=cfg.pretrain_batch,
        shuffle=True,
        drop_last=True,
        num_workers=min(4, 2),
        pin_memory=(device == "cuda"),
    )

    criterion = InfoNCELoss(temperature=cfg.temperature)
    optimizer = Adam(
        model.parameters(),
        lr=cfg.pretrain_lr,
        weight_decay=cfg.pretrain_wd,
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=cfg.pretrain_epochs)

    best_loss = float("inf")

    for epoch in range(1, cfg.pretrain_epochs + 1):
        model.train()
        total_loss = 0.0
        total_acc  = 0.0
        n_batches  = 0

        for x_in, x_out in loader:
            x_in  = x_in.to(device)
            x_out = x_out.to(device)

            optimizer.zero_grad()

            # Forward: backbone h_* and projection z_*
            # Only z_* goes into the loss; h_* are not used during pre-training
            _, _, z_in, z_out = model(x_in, x_out)

            loss = criterion(z_in, z_out)
            loss.backward()

            # Gradient clipping — protects against spikes in early training
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()

            total_loss += loss.item()
            # Detach before retrieval metric (no grad needed)
            total_acc  += criterion.top1_retrieval(z_in.detach(), z_out.detach())
            n_batches  += 1

        scheduler.step()
        epoch_loss = total_loss / n_batches
        epoch_acc  = total_acc  / n_batches

        if epoch % log_every == 0:
            logger.info(
                "Pretrain %3d/%d  loss=%.4f  retrieval_acc=%.2f  lr=%.2e",
                epoch, cfg.pretrain_epochs,
                epoch_loss, epoch_acc,
                scheduler.get_last_lr()[0],
            )

        if epoch_loss < best_loss:
            best_loss = epoch_loss
            if checkpoint_dir:
                _save(model, checkpoint_dir / "pretrain_best.pt")

        if checkpoint_dir and epoch % 10 == 0:
            # Save every 10 epochs for t-SNE visualisation checkpoints
            _save(model, checkpoint_dir / f"pretrain_ep{epoch:03d}.pt")

    logger.info("Pre-training complete. Best loss: %.4f", best_loss)
    return model


# ─── Phase 2: Fine-tuning ─────────────────────────────────────────────────────

def finetune(
    backbone:        ContrastiveBeehiveModel,
    dataset:         LabeledBeehiveDataset,
    *,
    cfg:             TrainConfig  = TRAIN_CFG,
    device:          str          = "cpu",
    checkpoint_dir:  Optional[Path] = None,
) -> BeehiveFineTuner:
    """
    Fine-tune a pre-trained backbone on labelled hive events.

    Combined loss:
    ───────────────
    total = λ × SupConLoss + (1-λ) × CrossEntropyLoss,  λ = cfg.supcon_weight

    Why both losses?
    ─────────────────
    SupCon:         pushes same-class embeddings together on the unit sphere.
                    Good at learning geometry but doesn't directly optimise
                    for argmax accuracy.
    CrossEntropy:   directly optimises for correct class prediction.
                    Ignores embedding geometry; can produce bad representations
                    if used alone with sparse labels.
    Combined:       SupCon shapes the space, CE drives the decision boundary.
                    Together they converge faster and to better minima than either alone.

    The backbone is frozen by BeehiveFineTuner — only the ClassifierHead
    (~2,240 params) is updated. If accuracy plateaus around epoch 60-70,
    call finetuner.unfreeze_backbone() and continue with lr=1e-5.
    """
    finetuner = BeehiveFineTuner(backbone).to(device)
    logger.info(
        "Fine-tuner: %d trainable / %d total params",
        finetuner.n_trainable, finetuner.n_total,
    )

    # BalancedClassSampler: ensures every class appears in every batch.
    # Without this, rare classes form no positive pairs and get zero gradient.
    sampler = BalancedClassSampler(dataset.labels, cfg.samples_per_class)
    loader  = DataLoader(
        dataset,
        batch_size=cfg.finetune_batch,
        sampler=sampler,
        drop_last=True,
        num_workers=min(4, 2),
        pin_memory=(device == "cuda"),
    )

    supcon_loss = SupConLoss(temperature=cfg.temperature)
    ce_loss     = nn.CrossEntropyLoss()

    # Only train the classifier — backbone.parameters() has requires_grad=False
    optimizer = Adam(finetuner.classifier.parameters(), lr=cfg.finetune_lr)
    scheduler = CosineAnnealingLR(optimizer, T_max=cfg.finetune_epochs)

    best_acc = 0.0

    for epoch in range(1, cfg.finetune_epochs + 1):
        finetuner.train()
        total_loss = 0.0
        correct, total = 0, 0

        for x_in, x_out, labels in loader:
            x_in   = x_in.to(device)
            x_out  = x_out.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()

            # ── Backbone forward (no gradient accumulation — frozen) ──────
            h_in, h_out = finetuner.backbone.encode(x_in, x_out)
            # h_in / h_out are detached from the backbone's computation graph
            # because backbone parameters have requires_grad=False.
            # PyTorch doesn't allocate gradient buffers for frozen params,
            # so this is as efficient as using torch.no_grad() on the backbone.

            # ── Classifier forward (gradients DO flow here) ───────────────
            logits = finetuner.classifier(h_in, h_out)

            # ── SupCon: operate on the concatenated, L2-normalised backbone ─
            # Concatenate inside + outside embeddings → 64-d vector
            # L2-normalise before SupConLoss (the formula requires unit vectors)
            embeddings = F.normalize(
                torch.cat([h_in, h_out], dim=-1), dim=-1
            )  # (B, 64), unit sphere
            loss_sc = supcon_loss(embeddings, labels)

            # ── CrossEntropy: operate on raw logits ───────────────────────
            loss_ce = ce_loss(logits, labels)

            # ── Combined loss ─────────────────────────────────────────────
            # λ=0.5 by default: both losses contribute equally.
            # If swarming/attack are hard to distinguish:
            #   increase λ (more contrastive pressure) or add class weights to CE.
            loss = cfg.supcon_weight * loss_sc + (1.0 - cfg.supcon_weight) * loss_ce
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct    += (logits.argmax(1) == labels).sum().item()
            total      += labels.size(0)

        scheduler.step()
        acc = correct / total if total > 0 else 0.0

        if epoch % 10 == 0:
            logger.info(
                "Finetune %3d/%d  loss=%.4f  acc=%.3f",
                epoch, cfg.finetune_epochs,
                total_loss / len(loader), acc,
            )
            # Per-class accuracy check — useful to catch classes that were
            # never learned (e.g., "queenless" with only 10 labelled events)
            if epoch % 20 == 0:
                _log_per_class_acc(finetuner, loader, device)

        if acc > best_acc:
            best_acc = acc
            if checkpoint_dir:
                _save(finetuner, checkpoint_dir / "finetune_best.pt")

    logger.info("Fine-tuning complete. Best accuracy: %.3f", best_acc)
    return finetuner


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _save(model: nn.Module, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)
    logger.debug("Saved checkpoint → %s", path)


def load_pretrained(
    model: ContrastiveBeehiveModel,
    path:  str | Path,
    device: str = "cpu",
) -> ContrastiveBeehiveModel:
    """Load a pre-training checkpoint into a ContrastiveBeehiveModel."""
    state = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(state)
    logger.info("Loaded pre-trained weights ← %s", path)
    return model.to(device)


def load_finetuned(
    finetuner: BeehiveFineTuner,
    path:      str | Path,
    device:    str = "cpu",
) -> BeehiveFineTuner:
    """Load a fine-tuning checkpoint into a BeehiveFineTuner."""
    state = torch.load(path, map_location=device, weights_only=True)
    finetuner.load_state_dict(state)
    logger.info("Loaded fine-tuned weights ← %s", path)
    return finetuner.to(device)


@torch.no_grad()
def _log_per_class_acc(
    finetuner: BeehiveFineTuner,
    loader:    DataLoader,
    device:    str,
) -> None:
    """Log per-class accuracy (useful to catch classes that were never learned)."""
    finetuner.eval()
    per_class_correct = {i: 0 for i in range(len(HIVE_STATES))}
    per_class_total   = {i: 0 for i in range(len(HIVE_STATES))}

    for x_in, x_out, labels in loader:
        x_in, x_out, labels = x_in.to(device), x_out.to(device), labels.to(device)
        preds = finetuner(x_in, x_out).argmax(1)
        for true_cls in labels.unique().tolist():
            mask = labels == true_cls
            per_class_correct[true_cls] += (preds[mask] == labels[mask]).sum().item()
            per_class_total[true_cls]   += mask.sum().item()

    for cls, name in enumerate(HIVE_STATES):
        n = per_class_total[cls]
        if n > 0:
            acc = per_class_correct[cls] / n
            logger.info("  %-20s  acc=%.2f  (%d samples)", name, acc, n)
    finetuner.train()
