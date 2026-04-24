# Trace Taxonomy v1 + Opening-Aware Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar trazas CAD de `wall`, `door` y `window` en el catálogo curado, hacer que el wall graph use solo trazas de pared, y mostrar visualmente doors/windows separados en el inspector temporal.

**Architecture:** El slice agrega una taxonomía general de trazas al catálogo (`trace_kind`), pero mantiene el wall graph apoyado exclusivamente en trazas `wall`. La curación deja de depender solo del `floor_plan.entities` normalizado para extraer paredes y además inspecciona el DXF fuente para capturar trazas de `DOORS` y `WINS/WIN`. El inspector consume la fixture expandida y deja prender/apagar `walls`, `doors` y `windows` por separado para validar visualmente que openings no contaminan paredes.

**Tech Stack:** Python, ezdxf, pydantic, pytest, TypeScript, React 19, Vitest, Testing Library.

---

### Task 1: Red test para taxonomía de trazas y filtrado wall-only
- `tests/test_floor_plan_catalog_curator.py`
- `tests/test_floor_plan_catalog_wall_graph.py`
- `backend/floor_plan_catalog/contracts.py`
- `backend/floor_plan_catalog/curator.py`

### Task 2: Curador opening-aware desde DXF fuente
- extraer trazas `wall/door/window` con `trace_kind`
- regenerar `D:\PointAIData\PLANS\catalog\seminole-2000.json`

### Task 3: Wall graph wall-only
- `backend/floor_plan_catalog/wall_graph.py`
- asegurar que soporte geométrico ignore `door/window`

### Task 4: Inspector visual opening-aware
- `frontend/src/features/catalogInspector/types.ts`
- `CatalogInspectorCanvas.tsx`
- `CatalogInspectorPage.tsx`
- `CatalogInspectorSidebar.tsx`
- `CatalogInspectorPage.test.tsx`

### Task 5: Fixture + verificación + commit
- export fixture real
- correr pytest/vitest focalizados
- commit convencional
