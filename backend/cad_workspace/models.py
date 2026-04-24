from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedCadEntity:
    type: str
    layer: str
    bbox: dict[str, float]
    origin: str | None = None
    start: dict[str, float] | None = None
    end: dict[str, float] | None = None
    points: tuple[dict[str, float], ...] = ()
    text: str | None = None
    position: dict[str, float] | None = None


@dataclass(frozen=True)
class CadView:
    role: str
    bbox: dict[str, float] | None
    entities: tuple[ExtractedCadEntity, ...]


@dataclass(frozen=True)
class ExtractedMeasurements:
    width: float
    height: float
    source: str


@dataclass(frozen=True)
class ExtractedRoom:
    name: str
    polygon: tuple[dict[str, float], ...]
    bbox: dict[str, float]
    centroid: dict[str, float]
    width: float
    height: float
    area: float
    measurement_source: str
