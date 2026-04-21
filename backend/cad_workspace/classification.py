from __future__ import annotations

from collections.abc import Callable

from .models import ExtractedCadEntity


def assign_floor_and_site_clusters(
    clusters: list[list[ExtractedCadEntity]],
    *,
    parse_dimension_text: Callable[[str], float | None],
    is_room_label_entity: Callable[[ExtractedCadEntity], bool],
) -> tuple[list[ExtractedCadEntity], list[ExtractedCadEntity], str]:
    if not clusters:
        return [], [], "unavailable"

    floor_anchor_index = find_cluster_by_anchor(clusters, "FLOOR PLAN")
    site_anchor_index = find_cluster_by_anchor(clusters, "SITE PLAN")

    floor_index = _find_cluster_with_floor_geometry(clusters)
    if floor_index is None:
        floor_index = floor_anchor_index
    if floor_index is None:
        floor_index = 0

    site_index = _find_cluster_with_site_geometry(clusters)
    if site_index is None:
        site_index = site_anchor_index
    if site_index is None:
        remaining = [idx for idx in range(len(clusters)) if idx != floor_index]
        site_index = remaining[0] if remaining else None

    floor_indexes = {floor_index}
    if floor_anchor_index is not None:
        floor_indexes.add(floor_anchor_index)
    floor_indexes.update(
        _find_floor_support_clusters(
            clusters,
            parse_dimension_text=parse_dimension_text,
            is_room_label_entity=is_room_label_entity,
        )
    )

    site_indexes: set[int] = set()
    if site_index is not None:
        site_indexes.add(site_index)
    if site_anchor_index is not None:
        site_indexes.add(site_anchor_index)

    floor_cluster = _merge_cluster_indexes(clusters, floor_indexes)
    site_cluster = _merge_cluster_indexes(clusters, site_indexes)

    assignment_mode = "spatial_cluster_split"
    if (
        floor_index == site_index
        or floor_anchor_index not in {None, floor_index}
        or site_anchor_index not in {None, site_index}
        or any(index not in {floor_index, floor_anchor_index} for index in floor_indexes)
    ):
        assignment_mode = "semantic_layer_split"

    return floor_cluster, site_cluster, assignment_mode


def cluster_score(entities: list[ExtractedCadEntity]) -> tuple[float, int]:
    if not entities:
        return (0.0, 0)
    min_x = min(entity.bbox["x1"] for entity in entities)
    min_y = min(entity.bbox["y1"] for entity in entities)
    max_x = max(entity.bbox["x2"] for entity in entities)
    max_y = max(entity.bbox["y2"] for entity in entities)
    area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
    return (area, len(entities))


def find_cluster_by_anchor(clusters: list[list[ExtractedCadEntity]], anchor: str) -> int | None:
    upper_anchor = anchor.upper()
    for index, cluster in enumerate(clusters):
        for entity in cluster:
            if entity.type == "text" and entity.text and upper_anchor in entity.text.upper():
                return index
    return None


def is_floor_wall_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    if "WALL" not in upper:
        return False
    blocked = ("ELECTRICAL", "WIRE", "DUCT", "HATCH")
    return not any(token in upper for token in blocked)


def is_site_geometry_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    keywords = ("SETBACK", "PROP", "SITE", "LOT", "BUILD", "EASE")
    return any(keyword in upper for keyword in keywords)


def is_annotation_geometry_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    keywords = ("TEXT", "DIM", "ROOM", "NOTE", "ANNO", "LABEL")
    return any(keyword in upper for keyword in keywords)


def is_room_closure_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    keywords = ("DOOR", "WIND", "OPEN", "SEPAR", "COL")
    return any(keyword in upper for keyword in keywords)


def is_property_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    return "PROP" in upper or "LOT" in upper


def is_buildable_layer(layer: str) -> bool:
    upper = (layer or "").upper()
    return "SETBACK" in upper or "BUILD" in upper


def is_floor_geometry_entity(entity: ExtractedCadEntity) -> bool:
    return (
        entity.type in {"line", "polyline"}
        and entity.origin != "DIMENSION"
        and is_floor_wall_layer(entity.layer)
    )


def is_floor_candidate_geometry_entity(entity: ExtractedCadEntity) -> bool:
    return (
        entity.type in {"line", "polyline"}
        and entity.origin != "DIMENSION"
        and not is_site_geometry_layer(entity.layer)
        and not is_annotation_geometry_layer(entity.layer)
    )


def is_site_geometry_entity(entity: ExtractedCadEntity) -> bool:
    return entity.type in {"line", "polyline"} and entity.origin != "DIMENSION" and is_site_geometry_layer(entity.layer)


def _find_cluster_with_floor_geometry(clusters: list[list[ExtractedCadEntity]]) -> int | None:
    exact = _find_cluster_with_geometry(clusters, is_floor_geometry_entity)
    if exact is not None:
        return exact
    return _find_cluster_with_geometry(clusters, is_floor_candidate_geometry_entity)


def _find_cluster_with_site_geometry(clusters: list[list[ExtractedCadEntity]]) -> int | None:
    return _find_cluster_with_geometry(clusters, is_site_geometry_entity)


def _find_cluster_with_geometry(
    clusters: list[list[ExtractedCadEntity]],
    predicate: Callable[[ExtractedCadEntity], bool],
) -> int | None:
    matches = [index for index, cluster in enumerate(clusters) if any(predicate(entity) for entity in cluster)]
    if not matches:
        return None
    return max(matches, key=lambda index: cluster_score(clusters[index]))


def _find_floor_support_clusters(
    clusters: list[list[ExtractedCadEntity]],
    *,
    parse_dimension_text: Callable[[str], float | None],
    is_room_label_entity: Callable[[ExtractedCadEntity], bool],
) -> set[int]:
    return {
        index
        for index, cluster in enumerate(clusters)
        if _is_dimension_support_cluster(cluster, parse_dimension_text=parse_dimension_text)
        or _is_room_label_support_cluster(cluster, is_room_label_entity=is_room_label_entity)
    }


def _is_dimension_support_cluster(
    cluster: list[ExtractedCadEntity],
    *,
    parse_dimension_text: Callable[[str], float | None],
) -> bool:
    saw_dimension = False
    for entity in cluster:
        if entity.type == "text" and entity.text:
            if "DIM" in (entity.layer or "").upper() or entity.origin == "DIMENSION":
                if parse_dimension_text(entity.text) is not None:
                    saw_dimension = True
    return saw_dimension


def _is_room_label_support_cluster(
    cluster: list[ExtractedCadEntity],
    *,
    is_room_label_entity: Callable[[ExtractedCadEntity], bool],
) -> bool:
    saw_room_label = False
    for entity in cluster:
        if entity.type != "text":
            return False
        if not is_room_label_entity(entity):
            return False
        saw_room_label = True
    return saw_room_label


def _merge_cluster_indexes(
    clusters: list[list[ExtractedCadEntity]],
    indexes: set[int],
) -> list[ExtractedCadEntity]:
    merged: list[ExtractedCadEntity] = []
    for index in sorted(indexes):
        if index < 0 or index >= len(clusters):
            continue
        merged.extend(clusters[index])
    return merged
