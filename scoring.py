"""Turns raw analyzer.py metrics into a 0-100 quality score, a
GOOD / REVIEW / POOR label, and human-readable reasons.

Thresholds below are reasonable defaults for general event photography
and are deliberately kept as simple module-level constants so they're
easy to tune without touching the scoring logic itself.
"""
from typing import Dict, List, Optional, Tuple

# --- Sharpness (Laplacian variance) ----------------------------------------
SHARPNESS_GOOD = 150.0   # at/above this -> full marks
SHARPNESS_POOR = 50.0    # at/below this -> essentially blurry

# --- Brightness (mean pixel intensity, 0-255) -------------------------------
BRIGHTNESS_MIN = 40.0
BRIGHTNESS_IDEAL_MIN = 80.0
BRIGHTNESS_IDEAL_MAX = 180.0
BRIGHTNESS_MAX = 220.0

# --- Exposure clipping (% of pixels blown out / crushed) -------------------
CLIP_WARN_PCT = 2.0
CLIP_BAD_PCT = 8.0

# --- Resolution --------------------------------------------------------------
MEGAPIXELS_GOOD = 3.0
MEGAPIXELS_POOR = 0.5

# --- How each factor contributes to the overall score -----------------------
WEIGHTS = {
    "sharpness": 0.40,
    "exposure": 0.30,
    "brightness": 0.20,
    "resolution": 0.10,
}

GOOD_THRESHOLD = 75
REVIEW_THRESHOLD = 50


def _score_sharpness(value: float) -> Tuple[float, Optional[str]]:
    if value >= SHARPNESS_GOOD:
        return 100.0, None
    if value <= SHARPNESS_POOR:
        score = max(0.0, (value / SHARPNESS_POOR) * 40)
        return score, "Photo looks blurry / out of focus"
    ratio = (value - SHARPNESS_POOR) / (SHARPNESS_GOOD - SHARPNESS_POOR)
    score = 40 + ratio * 60
    return score, ("Slightly soft focus" if ratio < 0.5 else None)


def _score_brightness(value: float) -> Tuple[float, Optional[str]]:
    if BRIGHTNESS_IDEAL_MIN <= value <= BRIGHTNESS_IDEAL_MAX:
        return 100.0, None
    if value < BRIGHTNESS_MIN:
        score = max(0.0, (value / BRIGHTNESS_MIN) * 40)
        return score, "Image is too dark"
    if value > BRIGHTNESS_MAX:
        score = max(0.0, 100 - ((value - BRIGHTNESS_MAX) / (255 - BRIGHTNESS_MAX)) * 60)
        return score, "Image is too bright"
    if value < BRIGHTNESS_IDEAL_MIN:
        ratio = (value - BRIGHTNESS_MIN) / (BRIGHTNESS_IDEAL_MIN - BRIGHTNESS_MIN)
        return 60 + ratio * 40, ("Slightly dark" if ratio < 0.5 else None)
    ratio = (BRIGHTNESS_MAX - value) / (BRIGHTNESS_MAX - BRIGHTNESS_IDEAL_MAX)
    return 60 + ratio * 40, ("Slightly bright" if ratio < 0.5 else None)


def _score_exposure(shadow_clip_pct: float, highlight_clip_pct: float) -> Tuple[float, Optional[str]]:
    worst = max(shadow_clip_pct, highlight_clip_pct)
    if worst < CLIP_WARN_PCT:
        return 100.0, None
    is_highlight = highlight_clip_pct >= shadow_clip_pct
    if worst >= CLIP_BAD_PCT:
        score = max(0.0, 40 - (worst - CLIP_BAD_PCT))
        reason = "Overexposed — blown-out highlights" if is_highlight else "Underexposed — crushed shadows"
        return score, reason
    ratio = (worst - CLIP_WARN_PCT) / (CLIP_BAD_PCT - CLIP_WARN_PCT)
    score = 100 - ratio * 60
    reason = "Some clipped highlights" if is_highlight else "Some clipped shadows"
    return score, reason


def _score_resolution(megapixels: float) -> Tuple[float, Optional[str]]:
    if megapixels >= MEGAPIXELS_GOOD:
        return 100.0, None
    if megapixels <= MEGAPIXELS_POOR:
        return 0.0, "Very low resolution"
    ratio = (megapixels - MEGAPIXELS_POOR) / (MEGAPIXELS_GOOD - MEGAPIXELS_POOR)
    return ratio * 100, ("Low resolution" if ratio < 0.5 else None)


def classify(score: float) -> str:
    if score >= GOOD_THRESHOLD:
        return "GOOD"
    if score >= REVIEW_THRESHOLD:
        return "REVIEW"
    return "POOR"


def compute_score(metrics: Dict) -> Dict:
    """Combine raw metrics (from analyzer.analyze_image) into a final
    score, label, and the reasons behind it.
    """
    sharp_score, sharp_reason = _score_sharpness(metrics["sharpness"])
    bright_score, bright_reason = _score_brightness(metrics["brightness"])
    exposure_score, exposure_reason = _score_exposure(
        metrics["shadow_clip_pct"], metrics["highlight_clip_pct"]
    )
    res_score, res_reason = _score_resolution(metrics["megapixels"])

    total = (
        sharp_score * WEIGHTS["sharpness"]
        + exposure_score * WEIGHTS["exposure"]
        + bright_score * WEIGHTS["brightness"]
        + res_score * WEIGHTS["resolution"]
    )
    total = round(max(0.0, min(100.0, total)))
    label = classify(total)

    reasons: List[str] = [
        r for r in (sharp_reason, exposure_reason, bright_reason, res_reason) if r
    ]
    if not reasons:
        reasons = ["Sharp, well exposed, and good resolution"]

    return {
        "score": total,
        "label": label,
        "reasons": reasons,
        "sub_scores": {
            "sharpness": round(sharp_score),
            "exposure": round(exposure_score),
            "brightness": round(bright_score),
            "resolution": round(res_score),
        },
    }
