from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paths import MorphologyPaths, ensure_output_dirs


def load_lcz_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _in_range(value: float, lo: float, hi: float) -> bool:
    if pd.isna(value):
        return False
    return lo <= float(value) <= hi


def _rule_classify(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    for rule in config["rule_order"]:
        reasons = []
        ok = True
        for field, bounds in rule["conditions"].items():
            value = float(row.get(field, np.nan))
            if not _in_range(value, float(bounds[0]), float(bounds[1])):
                ok = False
                break
            reasons.append(f"{field}={value:.3f} in [{bounds[0]}, {bounds[1]}]")
        if ok:
            return {
                "lcz_rule": rule["lcz"],
                "lcz_rule_confidence": float(rule.get("confidence", 0.6)),
                "lcz_rule_reasons": "; ".join(reasons),
            }
    return {
        "lcz_rule": config.get("default_lcz", "LCZ 9 - Sparsely built"),
        "lcz_rule_confidence": 0.45,
        "lcz_rule_reasons": "No explicit rule matched; default fallback.",
    }


def _vector(row: pd.Series, features: list[str], scales: dict[str, float]) -> np.ndarray:
    values = []
    for feature in features:
        scale = float(scales.get(feature, 1.0)) or 1.0
        value = float(row.get(feature, 0.0) or 0.0)
        if pd.isna(value):
            value = 0.0
        values.append(value / scale)
    return np.array(values, dtype=float)


def _softmax_neg_distance(distances: np.ndarray) -> np.ndarray:
    logits = -distances
    logits = logits - logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


def _confidence_level(prob: float, margin: float, entropy_norm: float, config: dict[str, Any]) -> str:
    high = config["confidence_levels"]["high"]
    med = config["confidence_levels"]["medium"]
    if prob >= high["min_top1_probability"] and margin >= high["min_margin"] and entropy_norm <= high["max_entropy"]:
        return "high"
    if prob >= med["min_top1_probability"] and margin >= med["min_margin"] and entropy_norm <= med["max_entropy"]:
        return "medium"
    return "low"


def _prototype_classify(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    features = config["prototype_features"]
    scales = config["feature_scales"]
    x = _vector(row, features, scales)
    names = list(config["prototypes"].keys())
    distances = []
    for name in names:
        proto = pd.Series(config["prototypes"][name])
        distances.append(float(np.linalg.norm(x - _vector(proto, features, scales))))
    dist = np.array(distances, dtype=float)
    probs = _softmax_neg_distance(dist)
    order = np.argsort(-probs)
    top1_i = int(order[0])
    top2_i = int(order[1]) if len(order) > 1 else top1_i
    entropy = float(-(probs * np.log(probs + 1e-12)).sum())
    entropy_norm = entropy / max(math.log(len(probs)), 1e-9)
    top1_prob = float(probs[top1_i])
    top2_prob = float(probs[top2_i])
    margin = top1_prob - top2_prob
    return {
        "lcz_probability_top1": names[top1_i],
        "lcz_probability_top2": names[top2_i],
        "lcz_top1_probability": top1_prob,
        "lcz_top2_probability": top2_prob,
        "lcz_top1_top2_margin": margin,
        "lcz_entropy": entropy,
        "lcz_entropy_norm": entropy_norm,
        "lcz_confidence_level": _confidence_level(top1_prob, margin, entropy_norm, config),
        "lcz_distance_top1": float(dist[top1_i]),
    }


def classify_lcz(paths: MorphologyPaths, config_path: str | Path | None = None) -> dict[str, Any]:
    ensure_output_dirs(paths)
    config_path = Path(config_path) if config_path else paths.config_dir / "lcz_thresholds.json"
    config = load_lcz_config(config_path)
    indicators_path = paths.morphology_dir / "morphology_indicators_250m.csv"
    df = pd.read_csv(indicators_path)
    rows = []
    for _, row in df.iterrows():
        rows.append({**row.to_dict(), **_rule_classify(row, config), **_prototype_classify(row, config)})
    out = pd.DataFrame(rows)
    csv_path = paths.lcz_dir / "lcz_classification_250m.csv"
    summary_path = paths.lcz_dir / "lcz_classification_summary.json"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary = {
        "status": "success",
        "config_path": str(config_path),
        "grid_count": len(out),
        "rule_counts": out["lcz_rule"].value_counts().to_dict(),
        "probability_counts": out["lcz_probability_top1"].value_counts().to_dict(),
        "confidence_counts": out["lcz_confidence_level"].value_counts().to_dict(),
        "outputs": {"lcz_csv": str(csv_path)},
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return summary
