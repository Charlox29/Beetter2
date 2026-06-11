"""
beehive/visualize.py
─────────────────────────────────────────────────────────────────────────────
Tools to monitor pre-training progress.

The primary tool is t-SNE: it projects high-dimensional embeddings down to 2D
for visual inspection. Run it every ~10 epochs during pre-training.

Expected progression:
  Epoch 10:  random cloud. Nothing to see yet — expected and fine.
  Epoch 50:  vague groupings. The model is starting to find structure.
  Epoch 100: loose clusters. Hive states visible but overlapping.
  Epoch 200: tight, well-separated blobs. Pre-training is working.

If you reach epoch 200 with only a random cloud, investigate:
  - Are your inside/outside packet pairs truly time-matched?
  - Is the normalizer fitted? (a missing fit produces z=0 for everything)
  - Try a larger batch size (128 or 256) for more negative pairs.

Dependencies: scikit-learn (for t-SNE), matplotlib (for plotting).
Both are development-only — not needed on the inference machine.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

from .model import ContrastiveBeehiveModel
from .data import BeehiveDataset, LabeledBeehiveDataset
from .config import HIVE_STATES

logger = logging.getLogger(__name__)


def compute_embeddings(
    model:   ContrastiveBeehiveModel,
    dataset: BeehiveDataset | LabeledBeehiveDataset,
    device:  str = "cpu",
    max_samples: int = 2000,
) -> tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    """
    Run the backbone (encoder only, no projection head) on a dataset
    and collect the resulting embeddings.

    Args:
        model:       Pre-trained ContrastiveBeehiveModel.
        dataset:     BeehiveDataset or LabeledBeehiveDataset.
        max_samples: Cap at this many samples to keep t-SNE fast.

    Returns:
        emb_in   (N, 32): inside backbone embeddings
        emb_out  (N, 32): outside backbone embeddings
        labels   (N,) integer class labels, or None if dataset is unlabelled
    """
    model.to(device).eval()
    loader = DataLoader(dataset, batch_size=256, shuffle=False)

    all_emb_in, all_emb_out = [], []
    all_labels = []
    n_collected = 0
    has_labels  = isinstance(dataset, LabeledBeehiveDataset)

    with torch.no_grad():
        for batch in loader:
            if n_collected >= max_samples:
                break

            if has_labels:
                x_in, x_out, labels = batch
                all_labels.append(labels.numpy())
            else:
                x_in, x_out = batch

            x_in  = x_in.to(device)
            x_out = x_out.to(device)

            h_in, h_out = model.encode(x_in, x_out)
            all_emb_in.append(h_in.cpu().numpy())
            all_emb_out.append(h_out.cpu().numpy())
            n_collected += len(x_in)

    emb_in  = np.concatenate(all_emb_in,  axis=0)[:max_samples]
    emb_out = np.concatenate(all_emb_out, axis=0)[:max_samples]
    labels  = np.concatenate(all_labels,  axis=0)[:max_samples] if has_labels else None

    return emb_in, emb_out, labels


def plot_tsne(
    model:    ContrastiveBeehiveModel,
    dataset:  BeehiveDataset | LabeledBeehiveDataset,
    epoch:    int,
    save_dir: Optional[Path] = None,
    device:   str = "cpu",
) -> None:
    """
    Compute t-SNE of backbone embeddings and save a PNG.

    The plot shows the CONCATENATED inside+outside embeddings (64-d projected to 2-d).
    If the dataset has labels, points are coloured by class; otherwise by which
    sensor (inside=teal, outside=purple).

    Args:
        model:    Pre-trained ContrastiveBeehiveModel.
        dataset:  Dataset to embed.
        epoch:    Used for the title and filename.
        save_dir: If set, saves to save_dir/tsne_ep{epoch:03d}.png
    """
    try:
        from sklearn.manifold import TSNE
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
    except ImportError:
        logger.warning(
            "scikit-learn or matplotlib not installed. "
            "Run: pip install scikit-learn matplotlib"
        )
        return

    logger.info("Computing t-SNE for epoch %d ...", epoch)
    emb_in, emb_out, labels = compute_embeddings(model, dataset, device)

    # t-SNE on concatenated embeddings (captures the relationship between the two views)
    # perplexity: roughly the expected number of neighbours per point.
    # 30 is a good default for datasets of 500–2000 points.
    combined = np.concatenate([emb_in, emb_out], axis=-1)  # (N, 64)
    tsne_xy  = TSNE(
        n_components=2,
        perplexity=min(30, len(combined) - 1),
        random_state=42,
        n_jobs=-1,
    ).fit_transform(combined)  # (N, 2)

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.set_title(f"Embedding space — epoch {epoch}", fontsize=13)
    ax.set_xlabel("t-SNE dim 1")
    ax.set_ylabel("t-SNE dim 2")
    ax.grid(True, alpha=0.3)

    if labels is not None:
        # Colour by class label
        colours = cm.tab10(np.linspace(0, 1, len(HIVE_STATES)))
        for cls_idx, cls_name in enumerate(HIVE_STATES):
            mask = labels == cls_idx
            if mask.any():
                ax.scatter(
                    tsne_xy[mask, 0], tsne_xy[mask, 1],
                    c=[colours[cls_idx]], label=cls_name,
                    s=20, alpha=0.7,
                )
        ax.legend(loc="upper right", fontsize=9)
    else:
        # Unlabelled: just plot all points in one colour
        ax.scatter(tsne_xy[:, 0], tsne_xy[:, 1], s=10, alpha=0.5, c="steelblue")

    plt.tight_layout()

    if save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        out = save_dir / f"tsne_ep{epoch:03d}.png"
        fig.savefig(out, dpi=150)
        logger.info("t-SNE saved → %s", out)
    else:
        plt.show()

    plt.close(fig)
