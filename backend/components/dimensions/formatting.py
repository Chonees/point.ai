from __future__ import annotations

AUDIT_GEOMETRY_TOLERANCE_PX = 1.0
AUDIT_GENERATED_GAP_TOLERANCE_PX = 1.0


def _fmt_inches(value: float) -> str:
    feet = int(value) // 12
    remaining = round(value - feet * 12)
    if remaining == 12:
        feet += 1
        remaining = 0
    return f"{feet}'-{remaining}\""


def _audit_dim_status(*, geometry_closure_error_px: float, generated_gap_px: float) -> str:
    if geometry_closure_error_px <= AUDIT_GEOMETRY_TOLERANCE_PX:
        if generated_gap_px <= AUDIT_GENERATED_GAP_TOLERANCE_PX:
            return "pass"
        return "warn"
    return "fail"
