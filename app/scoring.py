from app.schemas import ScoreBand

HIGH_THRESHOLD = 0.80
MEDIUM_THRESHOLD = 0.65
LOW_THRESHOLD = 0.50

SCORE_BANDS = [
    ScoreBand(label="High", min_score=HIGH_THRESHOLD, max_score=None),
    ScoreBand(label="Medium", min_score=MEDIUM_THRESHOLD, max_score=HIGH_THRESHOLD),
    ScoreBand(label="Low", min_score=LOW_THRESHOLD, max_score=MEDIUM_THRESHOLD),
    ScoreBand(label="Not surfaced", min_score=0.0, max_score=LOW_THRESHOLD),
]


def score_label(score: float) -> str:
    if score >= HIGH_THRESHOLD:
        return "High"
    if score >= MEDIUM_THRESHOLD:
        return "Medium"
    if score >= LOW_THRESHOLD:
        return "Low"
    return "Not surfaced"
