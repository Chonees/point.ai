# Supabase Migrations Log

Log de cambios aplicados a la DB de Supabase. Corré cada migración en orden vía
**Supabase Dashboard → SQL Editor → New query → Run**.

Todas las migraciones son **idempotentes** (usan `if not exists`) así que se
pueden correr múltiples veces sin romper nada.

---

## 0001 — Per-plan editor visibility + total floor area

**Fecha:** 2026-04-13
**Branch:** `feature/finalyouches`
**Motivo:** Persistir preferencias del editor 2D (botón `Hide` con checkboxes)
y el input `Total area` del Plan Metadata para que queden como el usuario los
dejó al reabrir un plan.

### SQL

```sql
-- Columna para el toggle "Hide" de visibility por capa (bg, regions, walls, doors, windows, labels, separators)
alter table plans
  add column if not exists editor_visibility jsonb not null default
  '{"bg":true,"regions":true,"walls":true,"doors":true,"windows":true,"labels":true,"separators":true}'::jsonb;

-- Columna para el "Total area" del Plan Metadata (scale calibration)
alter table plans
  add column if not exists total_sqft real;
```

### Columnas

| Columna | Tipo | Nullable | Default | Qué guarda |
|---------|------|----------|---------|------------|
| `editor_visibility` | `jsonb` | no | todos `true` | 7 flags de visibilidad del editor 2D |
| `total_sqft` | `real` | sí | `NULL` | Sqft total del plano (para calibración de escala) |

### Archivos frontend afectados

- `frontend/src/types.ts` — `Visibility` + `DEFAULT_VISIBILITY`
- `frontend/src/lib/database.types.ts` — PlanRow, Insert, Update
- `frontend/src/features/projects/project.types.ts` — `PlanScene.visibility`, `PlanData.totalSqft`
- `frontend/src/features/projects/project.mappers.ts` — `rowToPlan`
- `frontend/src/features/projects/usePlanSave.ts` — serializa `totalSqft` + `editor_visibility`, acumula updates en debounce
- `frontend/src/components/UploadPanel.tsx` — carga y notifica cambios
- `frontend/src/components/OverlayEditor/*` — botón `Hide` con panel de checkboxes

---

## Cómo agregar una nueva migración

1. Agregar el SQL al final de `supabase-schema.sql` (bajo `-- Migrations for existing databases (idempotent)`)
2. Agregar una sección en este archivo con número siguiente (`## 0002 — …`) con:
   - Fecha (ISO)
   - Branch / feature
   - Motivo
   - SQL exacto corrido
   - Descripción de columnas nuevas / modificadas
   - Archivos frontend/backend afectados
3. Correr el SQL en Supabase Dashboard
4. Confirmar que el frontend compile y que la feature persiste
