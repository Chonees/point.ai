# Floor Plan Catalog Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear el primer pipeline offline de curado para convertir un DXF de floor plan en un `FloorPlanCatalogSeed` usable por el MVP catalog-first, arrancando por `SEMINOLE2000` y dejando a `SANTA-BARBARA` auditado con flags honestos.

**Architecture:** Este slice NO intenta resolver todavía reconstrucción completa de walls/openings. Primero construye un bounded context nuevo (`backend/floor_plan_catalog/`) que toma la extracción CAD existente, la cruza con auditoría directa del DXF y genera un JSON canónico con rooms, footprint, metadata CAD, blocks, quality flags y readiness. El resultado debe ser suficientemente rico para seleccionar floor plans del catálogo y suficientemente honesto para bloquear los que todavía necesitan curado extra.

**Tech Stack:** Python, FastAPI codebase patterns, ezdxf, existing `backend.cad_workspace.extractor`, pytest.

---

## File Structure

### New files
- `backend/floor_plan_catalog/__init__.py` — paquete del bounded context nuevo.
- `backend/floor_plan_catalog/contracts.py` — dataclasses / typed models del `FloorPlanCatalogSeed`, rooms, fixtures summary y readiness flags.
- `backend/floor_plan_catalog/audit.py` — lectura directa DXF para resumir layers, tipos de entidad, block refs y labels de room.
- `backend/floor_plan_catalog/curator.py` — orquesta `extract_cad_file(...)` + `audit_floor_plan_source(...)` y genera el seed canónico.
- `scripts/curate_floor_plan_catalog.py` — CLI offline para curar uno o varios DXF a JSON.
- `tests/test_floor_plan_catalog_audit.py` — tests del auditor DXF.
- `tests/test_floor_plan_catalog_curator.py` — tests del curador y readiness flags.

### Existing files to modify
- `backend/cad_workspace/extractor.py` — solo si hace falta exponer metadata mínima ya disponible sin duplicar lógica; mantener el cambio acotado.
- `MVP.md` — agregar referencia al artefacto `FloorPlanCatalogSeed` una vez implementado.

---

### Task 1: Definir el contrato `FloorPlanCatalogSeed`

**Files:**
- Create: `backend/floor_plan_catalog/contracts.py`
- Test: `tests/test_floor_plan_catalog_curator.py`

- [ ] **Step 1: Write the failing contract test**

```python
from backend.floor_plan_catalog.contracts import FloorPlanCatalogSeed


def test_floor_plan_catalog_seed_exposes_minimum_curated_shape():
    seed = FloorPlanCatalogSeed(
        floor_plan_id="seminole-2000",
        name="SEMINOLE2000",
        source_path="D:/PointAIData/PLANS/originalFloorPlans/SEMINOLE2000.dxf",
        canonical_unit="inch",
        footprint_bbox={"width": 468.0, "height": 792.0},
        rooms=[],
        source_layers=[],
        block_refs=[],
        readiness={
            "status": "ready_for_catalog",
            "issues": [],
        },
    )

    payload = seed.model_dump()

    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["canonical_unit"] == "inch"
    assert payload["readiness"]["status"] == "ready_for_catalog"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: FAIL with `ModuleNotFoundError` for `backend.floor_plan_catalog`

- [ ] **Step 3: Write minimal contracts**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogReadiness(BaseModel):
    status: str
    issues: list[str] = Field(default_factory=list)


class CatalogBBox(BaseModel):
    width: float
    height: float


class CatalogRoom(BaseModel):
    name: str
    width: float
    height: float
    area: float
    measurement_source: str


class FloorPlanCatalogSeed(BaseModel):
    floor_plan_id: str
    name: str
    source_path: str
    canonical_unit: str
    footprint_bbox: CatalogBBox
    rooms: list[CatalogRoom] = Field(default_factory=list)
    source_layers: list[str] = Field(default_factory=list)
    block_refs: list[str] = Field(default_factory=list)
    readiness: CatalogReadiness
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/__init__.py backend/floor_plan_catalog/contracts.py tests/test_floor_plan_catalog_curator.py
git commit -m "feat: add floor plan catalog seed contracts"
```

---

### Task 2: Auditar layers, blocks y labels directamente desde DXF

**Files:**
- Create: `backend/floor_plan_catalog/audit.py`
- Test: `tests/test_floor_plan_catalog_audit.py`

- [ ] **Step 1: Write the failing audit test**

```python
from pathlib import Path

from backend.floor_plan_catalog.audit import audit_floor_plan_source


def test_audit_floor_plan_source_collects_layers_blocks_and_room_labels(tmp_path: Path):
    dxf_path = tmp_path / "sample-floor.dxf"
    # helper fixture writer lives in the test file
    write_sample_floor_plan_dxf(dxf_path)

    audit = audit_floor_plan_source(dxf_path)

    assert "WALLS" in audit.source_layers
    assert "ROOM LBLS" in audit.source_layers
    assert audit.block_refs["TOILET1"] == 1
    assert "KITCHEN" in audit.room_labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_audit.py -q`
Expected: FAIL with `ImportError` or missing function

- [ ] **Step 3: Write the DXF audit helper**

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path

import ezdxf
from pydantic import BaseModel, Field


class FloorPlanSourceAudit(BaseModel):
    source_layers: list[str] = Field(default_factory=list)
    entity_types: dict[str, int] = Field(default_factory=dict)
    block_refs: dict[str, int] = Field(default_factory=dict)
    room_labels: list[str] = Field(default_factory=list)


def audit_floor_plan_source(path: Path) -> FloorPlanSourceAudit:
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    layer_counts = Counter()
    type_counts = Counter()
    block_refs = Counter()
    room_labels: list[str] = []

    for entity in msp:
        layer = str(getattr(entity.dxf, "layer", "0") or "0")
        layer_counts[layer] += 1
        type_counts[entity.dxftype()] += 1

        if entity.dxftype() == "INSERT":
            block_refs[str(entity.dxf.name)] += 1

        if entity.dxftype() in {"TEXT", "MTEXT"}:
            text = entity.plain_text() if hasattr(entity, "plain_text") else str(entity.dxf.text)
            normalized = " ".join(text.upper().split())
            if "ROOM" in layer.upper() and normalized:
                room_labels.append(normalized)

    return FloorPlanSourceAudit(
        source_layers=sorted(layer_counts.keys()),
        entity_types=dict(type_counts),
        block_refs=dict(block_refs),
        room_labels=room_labels,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_audit.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/floor_plan_catalog/audit.py tests/test_floor_plan_catalog_audit.py
git commit -m "feat: audit floor plan cad metadata"
```

---

### Task 3: Curar un DXF a `FloorPlanCatalogSeed`

**Files:**
- Create: `backend/floor_plan_catalog/curator.py`
- Modify: `backend/floor_plan_catalog/contracts.py`
- Test: `tests/test_floor_plan_catalog_curator.py`

- [ ] **Step 1: Write the failing curator test**

```python
from pathlib import Path

from backend.floor_plan_catalog.curator import curate_floor_plan_seed


def test_curate_floor_plan_seed_merges_extraction_and_audit(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="seminole-2000", name="SEMINOLE2000")

    assert seed.floor_plan_id == "seminole-2000"
    assert seed.footprint_bbox.width == 468.0
    assert len(seed.rooms) == 2
    assert seed.rooms[0].name == "BEDROOM 2"
    assert "WALLS" in seed.source_layers
    assert seed.readiness.status == "ready_for_catalog"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: FAIL because `curate_floor_plan_seed` does not exist

- [ ] **Step 3: Write the curator**

```python
from __future__ import annotations

from pathlib import Path
from slugify import slugify

from backend.cad_workspace.extractor import extract_cad_file

from .audit import audit_floor_plan_source
from .contracts import CatalogBBox, CatalogReadiness, CatalogRoom, FloorPlanCatalogSeed


def curate_floor_plan_seed(path: Path, *, floor_plan_id: str | None = None, name: str | None = None) -> FloorPlanCatalogSeed:
    extracted = extract_cad_file(path, source_name=path.name)
    audit = audit_floor_plan_source(path)
    floor = extracted["floor_plan"]

    rooms = [
        CatalogRoom(
            name=room["name"],
            width=room["width"],
            height=room["height"],
            area=room["area"],
            measurement_source=room["measurement_source"],
        )
        for room in floor.get("rooms", [])
    ]

    readiness = _build_readiness(rooms=rooms, warnings=extracted.get("warnings", []))

    bbox = floor.get("bbox") or {"width": 0.0, "height": 0.0}
    return FloorPlanCatalogSeed(
        floor_plan_id=floor_plan_id or slugify(path.stem),
        name=name or path.stem,
        source_path=str(path),
        canonical_unit=extracted["canonical_unit"],
        footprint_bbox=CatalogBBox(width=bbox["width"], height=bbox["height"]),
        rooms=rooms,
        source_layers=audit.source_layers,
        block_refs=sorted(audit.block_refs.keys()),
        readiness=readiness,
    )


def _build_readiness(*, rooms: list[CatalogRoom], warnings: list[str]) -> CatalogReadiness:
    issues = list(warnings)
    if not rooms:
        issues.append("No rooms were extracted.")
    if len(rooms) < 6:
        issues.append("Room coverage is too low for a trusted catalog entry.")
    status = "ready_for_catalog" if not issues else "needs_manual_review"
    return CatalogReadiness(status=status, issues=issues)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: PASS

- [ ] **Step 5: Add a regression test for honest readiness flags**

```python
def test_curate_floor_plan_seed_marks_low_room_coverage_as_manual_review(tmp_path: Path):
    dxf_path = tmp_path / "weak-floor.dxf"
    write_sparse_room_floor_dxf(dxf_path)

    seed = curate_floor_plan_seed(dxf_path, floor_plan_id="santa-barbara", name="SANTA-BARBARA")

    assert seed.readiness.status == "needs_manual_review"
    assert "Room coverage is too low for a trusted catalog entry." in seed.readiness.issues
```

- [ ] **Step 6: Run test suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py tests/test_floor_plan_catalog_audit.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/floor_plan_catalog/contracts.py backend/floor_plan_catalog/curator.py tests/test_floor_plan_catalog_curator.py
git commit -m "feat: curate floor plan catalog seeds"
```

---

### Task 4: Agregar CLI offline para generar JSON curado

**Files:**
- Create: `scripts/curate_floor_plan_catalog.py`
- Modify: `backend/floor_plan_catalog/curator.py`
- Test: `tests/test_floor_plan_catalog_curator.py`

- [ ] **Step 1: Write the failing CLI test**

```python
import json
from pathlib import Path
from subprocess import run


def test_curate_floor_plan_catalog_cli_writes_seed_json(tmp_path: Path):
    dxf_path = tmp_path / "catalog-floor.dxf"
    write_dimensioned_room_floor_dxf(dxf_path)
    output_path = tmp_path / "seminole-2000.json"

    result = run(
        [
            ".\\.venv\\Scripts\\python.exe",
            "scripts/curate_floor_plan_catalog.py",
            str(dxf_path),
            "--floor-plan-id",
            "seminole-2000",
            "--name",
            "SEMINOLE2000",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["floor_plan_id"] == "seminole-2000"
    assert payload["readiness"]["status"] == "ready_for_catalog"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: FAIL because the script does not exist

- [ ] **Step 3: Write the CLI**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.floor_plan_catalog.curator import curate_floor_plan_seed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--floor-plan-id")
    parser.add_argument("--name")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    seed = curate_floor_plan_seed(
        Path(args.source),
        floor_plan_id=args.floor_plan_id,
        name=args.name,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(seed.model_dump_json(indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the CLI test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_floor_plan_catalog_curator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/curate_floor_plan_catalog.py tests/test_floor_plan_catalog_curator.py
git commit -m "feat: add floor plan catalog curation cli"
```

---

### Task 5: Curar y comparar los dos floor plans reales del seed dataset

**Files:**
- Modify: `MVP.md`
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Current State.md`
- Modify: `D:\obsidian\vault\01 - Projects\Point.ai\Implementation\2026-04-21 - Floor plan catalog audit - Seminole vs Santa Barbara.md`

- [ ] **Step 1: Run the curator on SEMINOLE2000**

Run:

```bash
.\.venv\Scripts\python.exe scripts/curate_floor_plan_catalog.py "D:\PointAIData\PLANS\originalFloorPlans\SEMINOLE2000.dxf" --floor-plan-id seminole-2000 --name SEMINOLE2000 --output "D:\PointAIData\PLANS\catalog\seminole-2000.json"
```

Expected:
- command exits `0`
- file `D:\PointAIData\PLANS\catalog\seminole-2000.json` exists
- readiness is `ready_for_catalog` or at least narrowly scoped

- [ ] **Step 2: Run the curator on SANTA-BARBARA**

Run:

```bash
.\.venv\Scripts\python.exe scripts/curate_floor_plan_catalog.py "D:\PointAIData\PLANS\originalFloorPlans\SANTA-BARBARA.dxf" --floor-plan-id santa-barbara --name SANTA-BARBARA --output "D:\PointAIData\PLANS\catalog\santa-barbara.json"
```

Expected:
- command exits `0`
- file `D:\PointAIData\PLANS\catalog\santa-barbara.json` exists
- readiness is `needs_manual_review`

- [ ] **Step 3: Update MVP and Obsidian with the real outputs**

```markdown
- add the exact JSON output paths
- record whether SEMINOLE2000 is the first trusted catalog seed
- record why SANTA-BARBARA remains flagged
```

- [ ] **Step 4: Commit**

```bash
git add MVP.md
git commit -m "docs: record seeded floor plan catalog outputs"
```

---

## Self-Review

### Spec coverage
- Catalog-first MVP direction is covered by Tasks 1–5.
- Real extraction/comparison of the two seed floor plans is covered by Task 5.
- Honest readiness / manual-review gating is covered by Task 3.
- This plan intentionally does **not** implement wall/opening ownership reconstruction yet; that remains a later subproject.

### Placeholder scan
- No TBD/TODO placeholders left.
- Every code-changing step includes concrete code.
- Every verification step includes exact commands.

### Type consistency
- Main artifact name stays consistent: `FloorPlanCatalogSeed`.
- Readiness contract stays consistent: `CatalogReadiness(status, issues)`.
- CLI and curator both use the same function: `curate_floor_plan_seed(...)`.

