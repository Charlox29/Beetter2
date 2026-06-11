"""
IA/fit_and_train.py
─────────────────────────────────────────────────────────────────────────────
One script for both training phases.

  Phase 1 — pre-train on unlabelled data (run this today):
      python fit_and_train.py --mode pretrain --csv data/hive1.csv

  Phase 2 — fine-tune on labelled events (run later, once you have 30+ per class):
      python fit_and_train.py --mode finetune --csv data/hive1_labeled.csv

Output layout (all relative to IA/):
  calibration/
    norm_in.json          z-score statistics for inside sensor  (frozen after fit)
    norm_out.json         z-score statistics for outside sensor
  checkpoints/
    pretrain_best.pt      best pre-training checkpoint
    pretrain_ep***.pt     checkpoint every 10 epochs (for t-SNE inspection)
    finetune_best.pt      best fine-tuning checkpoint  ← Flask loads this
  tsne/
    tsne_ep***.png        embedding visualisation plots (--tsne flag)
"""

import argparse
import logging
import sys
from pathlib import Path

from beehive import model
from beehive.config import TrainConfig
from beehive.train import finetune, pretrain

# ── make the beehive package importable from IA/ ──────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)


# ─── Phase 1: pre-training ────────────────────────────────────────────────────

def run_pretrain(args):
    import numpy as np
    import pandas as pd

    from beehive.data import _build_raw_arrays, FeatureNormalizer, BeehiveDataset
    from beehive.model import ContrastiveBeehiveModel
    from beehive.train import pretrain
    from beehive.config import MODEL_CFG

    # ── 1. Load CSV ──────────────────────────────────────────────────────────
    log.info("Loading %s", args.csv)
    df = pd.read_csv(args.csv)
    log.info("  %d rows  |  %d columns", *df.shape)

    if len(df) < 200:
        log.error("Only %d rows — need at least 200 to train meaningfully.", len(df))
        log.error("Run:  python tools/simulate.py --burst 2000  then re-export.")
        return

    # ── 2. Quick sanity check on the data ────────────────────────────────────
    log.info("Data snapshot:")
    check_cols = {
        't_in_C':         '°C inside T',
        'h_in_pct':       '% inside H',
        'dom_freq_in_hz': 'Hz inside freq',
        'rms_in':         'RMS inside (pre-log)',
        'mfcc_in_1':      'MFCC-1 inside',
    }
    for col, label in check_cols.items():
        if col in df.columns:
            s = df[col]
            log.info("  %-18s  mean=%7.2f  std=%6.2f  [%7.2f … %7.2f]",
                     label, s.mean(), s.std(), s.min(), s.max())

    mfcc_present = (df['mfcc_in_1'] != 0).mean()
    if mfcc_present < 0.01:
        log.warning("MFCC columns are all zero — using --allow-partial simulated data.")
        log.warning("The model will pre-train on 4 features; MFCC slots will learn later.")
    else:
        log.info("  %.0f%% of rows have real MFCC data.", mfcc_present * 100)

    # ── 3. Fit normalizers ───────────────────────────────────────────────────
    log.info("Fitting z-score normalizers on %d samples…", len(df))
    raw_in, raw_out = _build_raw_arrays(df)    # (N, 9) each, un-normalised

    norm_in  = FeatureNormalizer().fit(raw_in)
    norm_out = FeatureNormalizer().fit(raw_out)

    calib_dir = Path(args.calib_dir)
    calib_dir.mkdir(parents=True, exist_ok=True)
    norm_in.save( calib_dir / 'norm_in.json')
    norm_out.save(calib_dir / 'norm_out.json')
    log.info("Normalizers saved → %s/", calib_dir)

    # ── 4. Build dataset ─────────────────────────────────────────────────────
    dataset = BeehiveDataset(args.csv, norm_in, norm_out)

    # ── 5. Build model ───────────────────────────────────────────────────────
    model = ContrastiveBeehiveModel(MODEL_CFG)
    n_enc = sum(p.numel() for p in model.encoder_in.parameters())
    n_all = sum(p.numel() for p in model.parameters())
    log.info("Model: %d params per encoder, %d total", n_enc, n_all)

    # ── 6. Pre-train ─────────────────────────────────────────────────────────
    ckpt_dir = Path(args.ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    log.info("─" * 60)
    log.info("Pre-training for %d epochs on %d samples  (device=%s)",
             args.epochs, len(dataset), args.device)
    log.info("What to watch:")
    log.info("  loss        starts near ln(%d)=%.2f  (random baseline)",
             64, __import__('math').log(64))
    log.info("  retrieval   starts near 1/64=0.016 (random baseline)")
    log.info("  Good sign:  retrieval_acc > 0.50 by epoch 100")
    log.info("─" * 60)

    from beehive.config import TrainConfig

    cfg = TrainConfig()
    cfg.pretrain_epochs = args.epochs

    model = pretrain(
        model, dataset,
        cfg=cfg,
        device=args.device,
        checkpoint_dir=ckpt_dir,
        log_every=10,
    )
    # ── 7. t-SNE (optional) ──────────────────────────────────────────────────
    if args.tsne:
        _plot_tsne(model, dataset, args.epochs)

    log.info("─" * 60)
    log.info("Pre-training done.  Best checkpoint: %s/pretrain_best.pt", ckpt_dir)
    log.info("")
    log.info("Next steps:")
    log.info("  • Deploy the real prototype and collect a few weeks of data.")
    log.info("  • For each observed hive event (swarming, attack, …),")
    log.info("    note the timestamp and add a 'label' column to the CSV:")
    log.info("      0=normal  1=pre_swarming  2=swarming")
    log.info("      3=queen_competition  4=queenless  5=attack")
    log.info("  • Then run:  python fit_and_train.py --mode finetune --csv data/labeled.csv")


# ─── Phase 2: fine-tuning ─────────────────────────────────────────────────────

def run_finetune(args):
    import pandas as pd
    from collections import Counter

    from beehive.data import FeatureNormalizer, LabeledBeehiveDataset
    from beehive.model import ContrastiveBeehiveModel
    from beehive.train import finetune, load_pretrained
    from beehive.config import MODEL_CFG, HIVE_STATES

    calib_dir = Path(args.calib_dir)
    ckpt_dir  = Path(args.ckpt_dir)

    # ── Validate prerequisites ────────────────────────────────────────────────
    pretrain_ckpt = ckpt_dir / 'pretrain_best.pt'
    for f in [pretrain_ckpt, calib_dir/'norm_in.json', calib_dir/'norm_out.json']:
        if not f.exists():
            log.error("Missing required file: %s", f)
            log.error("Run --mode pretrain first.")
            return

    # ── Load normalizers ──────────────────────────────────────────────────────
    norm_in  = FeatureNormalizer.load(calib_dir / 'norm_in.json')
    norm_out = FeatureNormalizer.load(calib_dir / 'norm_out.json')

    # ── Load labeled CSV ──────────────────────────────────────────────────────
    log.info("Loading labeled CSV: %s", args.csv)
    df = pd.read_csv(args.csv)

    if 'label' not in df.columns:
        log.error("CSV must have a 'label' column (integer 0-%d).", len(HIVE_STATES) - 1)
        log.error("Label mapping:")
        for i, name in enumerate(HIVE_STATES):
            log.error("  %d = %s", i, name)
        return

    # ── Class distribution ────────────────────────────────────────────────────
    dist = Counter(int(v) for v in df['label'].values)
    log.info("Class distribution:")
    min_count = float('inf')
    for i, name in enumerate(HIVE_STATES):
        n    = dist.get(i, 0)
        bar  = '█' * min(n // 2, 25)
        warn = '  ⚠️  < 30 samples' if n < 30 else ''
        log.info("  [%d] %-20s  %3d  %s%s", i, name, n, bar, warn)
        min_count = min(min_count, n)

    if min_count < 10:
        log.warning("Some classes have very few samples. Fine-tuning may not converge well.")
        log.warning("Try to collect at least 30 labelled events per class.")

    # ── Load pre-trained backbone ─────────────────────────────────────────────
    log.info("Loading pre-trained backbone from %s", pretrain_ckpt)
    model = load_pretrained(
        ContrastiveBeehiveModel(MODEL_CFG), pretrain_ckpt, device=args.device
    )

    # ── Fine-tune ─────────────────────────────────────────────────────────────
    dataset   = LabeledBeehiveDataset(args.csv, norm_in, norm_out)
    cfg = TrainConfig()
    cfg.finetune_epochs = args.epochs

    finetuner = finetune(
        model, dataset,
        cfg=cfg,
        device=args.device,
        checkpoint_dir=ckpt_dir,
    )
    log.info("Fine-tuning done.  Best checkpoint: %s/finetune_best.pt", ckpt_dir)
    log.info("")
    log.info("To enable ML inference in Flask, add to app/.env:")
    log.info("  ML_ENABLED=1")

    if args.tsne:
        _plot_tsne(finetuner.backbone, dataset, args.epochs)


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _plot_tsne(model, dataset, epoch):
    try:
        from beehive.visualize import plot_tsne
        tsne_dir = Path('tsne')
        tsne_dir.mkdir(exist_ok=True)
        log.info("Generating t-SNE plot → tsne/tsne_ep%03d.png …", epoch)
        plot_tsne(model, dataset, epoch=epoch, save_dir=tsne_dir)
        log.info("t-SNE saved.")
    except ImportError:
        log.warning("t-SNE skipped — install scikit-learn and matplotlib:")
        log.warning("  pip install scikit-learn matplotlib")
    except Exception as e:
        log.warning("t-SNE failed: %s", e)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Beetter contrastive model trainer")
    p.add_argument('--mode',      required=True, choices=['pretrain', 'finetune'],
                   help="pretrain (Phase 1) or finetune (Phase 2)")
    p.add_argument('--csv',       required=True,
                   help="Path to the training CSV (from collect_training_data.py)")
    p.add_argument('--epochs',    type=int, default=None,
                   help="Number of epochs (default: 200 pretrain / 100 finetune)")
    p.add_argument('--device',    default='cpu',
                   help="'cpu' or 'cuda' (default: cpu)")
    p.add_argument('--calib-dir', default='calibration',
                   help="Where to save/load normalizer JSON files")
    p.add_argument('--ckpt-dir',  default='checkpoints',
                   help="Where to save model checkpoints")
    p.add_argument('--tsne',      action='store_true',
                   help="Generate a t-SNE plot of embeddings after training")
    args = p.parse_args()

    if args.epochs is None:
        args.epochs = 200 if args.mode == 'pretrain' else 100

    if args.mode == 'pretrain':
        run_pretrain(args)
    else:
        run_finetune(args)


if __name__ == '__main__':
    main()
