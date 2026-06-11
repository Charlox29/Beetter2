"""
beehive/
─────────────────────────────────────────────────────────────────────────────
Beehive IoT contrastive learning package.

Quick-start
───────────
    from beehive.model import ContrastiveBeehiveModel
    from beehive.data import FeatureNormalizer, BeehiveDataset
    from beehive.train import pretrain, finetune
    from beehive.inference import BeehiveInference

Two-phase training recap:
    Phase 1 — no labels, ~2000+ packets, ~200 epochs
        model   = ContrastiveBeehiveModel()
        dataset = BeehiveDataset("data.csv", norm_in, norm_out)
        model   = pretrain(model, dataset)

    Phase 2 — 30–50 labelled events per class, ~100 epochs
        dataset  = LabeledBeehiveDataset("data_labeled.csv", norm_in, norm_out)
        finetune = finetune(model, dataset)

    Inference — one call per incoming LoRa packet
        engine = BeehiveInference(finetuner, norm_in, norm_out)
        result = engine.infer(raw_31_bytes)
        if result.alert: send_notification(result.alert_reason)
"""

from .config import (
    HIVE_STATES, NUM_CLASSES,
    ModelConfig, TrainConfig, InferenceConfig, LoRaPacketConfig,
    MODEL_CFG, TRAIN_CFG, INFER_CFG, LORA_PKT_CFG,
)
from .data import (
    decode_packet, packet_to_raw_features,
    FeatureNormalizer,
    BeehiveDataset, LabeledBeehiveDataset,
    BalancedClassSampler,
)
from .model import (
    BeehiveEncoder, BeehiveCNNEncoder,
    ProjectionHead,
    ContrastiveBeehiveModel,
    ClassifierHead,
    BeehiveFineTuner,
)
from .losses import InfoNCELoss, SupConLoss
from .train import pretrain, finetune, load_pretrained, load_finetuned
from .inference import BeehiveInference, InferenceResult

__all__ = [
    # config
    "HIVE_STATES", "NUM_CLASSES",
    "ModelConfig", "TrainConfig", "InferenceConfig", "LoRaPacketConfig",
    "MODEL_CFG", "TRAIN_CFG", "INFER_CFG", "LORA_PKT_CFG",
    # data
    "decode_packet", "packet_to_raw_features",
    "FeatureNormalizer",
    "BeehiveDataset", "LabeledBeehiveDataset", "BalancedClassSampler",
    # model
    "BeehiveEncoder", "BeehiveCNNEncoder",
    "ProjectionHead",
    "ContrastiveBeehiveModel",
    "ClassifierHead",
    "BeehiveFineTuner",
    # losses
    "InfoNCELoss", "SupConLoss",
    # train
    "pretrain", "finetune", "load_pretrained", "load_finetuned",
    # inference
    "BeehiveInference", "InferenceResult",
]
