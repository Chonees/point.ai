from __future__ import annotations


UNIT_ALIASES = {
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "ft": "foot",
    "foot": "foot",
    "feet": "foot",
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "pixel": "pixel",
    "pixels": "pixel",
    "px": "pixel",
}

TO_INCH_FACTOR = {
    "inch": 1.0,
    "foot": 12.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "m": 39.37007874015748,
}


def normalize_unit_name(raw_unit: str | None, *, fallback: str | None = None) -> str | None:
    if isinstance(raw_unit, str):
        normalized = UNIT_ALIASES.get(raw_unit.strip().lower())
        if normalized is not None:
            return normalized
        stripped = raw_unit.strip().lower()
        if stripped:
            return stripped
    return fallback


def is_physical_unit(unit: str | None) -> bool:
    normalized = normalize_unit_name(unit)
    return normalized in TO_INCH_FACTOR


def canonical_internal_unit(unit: str | None, *, fallback: str) -> str:
    normalized = normalize_unit_name(unit, fallback=fallback)
    if is_physical_unit(normalized):
        return "inch"
    return normalized or fallback


def convert_value(value: float, *, from_unit: str | None, to_unit: str = "inch") -> float:
    source = normalize_unit_name(from_unit)
    target = normalize_unit_name(to_unit, fallback=to_unit)
    if source == target or source is None:
        return float(value)
    if source not in TO_INCH_FACTOR or target not in TO_INCH_FACTOR:
        return float(value)
    value_in_inches = float(value) * TO_INCH_FACTOR[source]
    return value_in_inches / TO_INCH_FACTOR[target]


def normalize_bbox(raw_bbox: dict[str, float] | None, *, from_unit: str | None, to_unit: str = "inch") -> dict[str, float] | None:
    if raw_bbox is None:
        return None
    return {
        "x1": convert_value(raw_bbox["x1"], from_unit=from_unit, to_unit=to_unit),
        "y1": convert_value(raw_bbox["y1"], from_unit=from_unit, to_unit=to_unit),
        "x2": convert_value(raw_bbox["x2"], from_unit=from_unit, to_unit=to_unit),
        "y2": convert_value(raw_bbox["y2"], from_unit=from_unit, to_unit=to_unit),
        "width": convert_value(raw_bbox["width"], from_unit=from_unit, to_unit=to_unit),
        "height": convert_value(raw_bbox["height"], from_unit=from_unit, to_unit=to_unit),
    }


def normalize_polygon(raw_polygon: list[dict] | None, *, from_unit: str | None, to_unit: str = "inch") -> list[dict[str, float]]:
    points = raw_polygon or []
    return [
        {
            "x": convert_value(float(point["x"]), from_unit=from_unit, to_unit=to_unit),
            "y": convert_value(float(point["y"]), from_unit=from_unit, to_unit=to_unit),
        }
        for point in points
    ]
