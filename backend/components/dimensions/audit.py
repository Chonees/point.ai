from __future__ import annotations

import backend.components.dimensions as _dims_pkg

from .formatting import _fmt_inches, _audit_dim_status, AUDIT_GEOMETRY_TOLERANCE_PX, AUDIT_GENERATED_GAP_TOLERANCE_PX


def _make_audit_summary() -> dict[str, object]:
    return {
        "window_chain_pass": 0,
        "window_chain_warn": 0,
        "window_chain_fail": 0,
        "windowless_wall_totals": 0,
        "audited_window_chains": 0,
        "max_generated_gap_px": 0.0,
        "max_generated_gap_in": 0.0,
        "max_geometry_closure_error_px": 0.0,
        "max_geometry_closure_error_in": 0.0,
        "overlapping_label_count": 0,
        "duplicated_region_count": 0,
    }


def _log_audit_summary(audit_summary: dict[str, object], measurement_context: dict | None) -> None:
    _dims_pkg.log_event(
        "dims_audit_summary",
        audited_window_chains=audit_summary["audited_window_chains"],
        window_chain_pass=audit_summary["window_chain_pass"],
        window_chain_warn=audit_summary["window_chain_warn"],
        window_chain_fail=audit_summary["window_chain_fail"],
        windowless_wall_totals=audit_summary["windowless_wall_totals"],
        max_generated_gap_px=round(audit_summary["max_generated_gap_px"], 4),
        max_generated_gap_in=round(audit_summary["max_generated_gap_in"], 4),
        max_geometry_closure_error_px=round(audit_summary["max_geometry_closure_error_px"], 4),
        max_geometry_closure_error_in=round(audit_summary["max_geometry_closure_error_in"], 4),
        overlapping_label_count=audit_summary["overlapping_label_count"],
        duplicated_region_count=audit_summary["duplicated_region_count"],
        calibration_mode=measurement_context.get("calibration_mode") if measurement_context else None,
    )
