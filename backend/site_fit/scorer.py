from __future__ import annotations


def score_candidate(candidate: dict) -> dict:
    scored = dict(candidate)
    scored["score"] = 1.0 if candidate.get("change_count", 0) == 0 else 0.5
    return scored

