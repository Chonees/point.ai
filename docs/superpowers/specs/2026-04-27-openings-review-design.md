# Openings Review Design

## Goal

Recuperar el flujo útil de puertas y ventanas del pipeline viejo sin revivir todo el editor manual: detección automática tipo legacy, revisión mínima en frontend, y aplicación de esas correcciones solo en la sesión actual al generar el DXF.

## Scope

- Restaurar auto-detección de `door` y `window` para `model_variant: "ensemble"`.
- Mostrar esas detecciones automáticamente apenas termina la inferencia.
- Permitir solo dos acciones humanas sobre openings:
  - mover libremente en el plano
  - eliminar
- No permitir crear nuevas openings.
- No persistir correcciones en proyecto por ahora.
- Aceptar falsos negativos del detector por esta iteración.

## Product Loop + Architecture

- **Product loop:** Loop 1 / floor plan curation.
- **Architecture layers touched:**
  - **Infrastructure:** backend de inferencia y DXF (`backend/ensemble_inference.py`, `backend/services/*`)
  - **Contracts:** modelos API (`backend/models.py`, `frontend/src/types.ts`)
  - **Application / Desktop UI:** flujo React de carga, revisión y export (`frontend/src/features/workspace/*`)

## Current Problem

Cuando sacamos la detección automática de openings del output productivo, el sistema quedó sin una etapa útil para puertas/ventanas. El pipeline viejo se sentía mejor porque no era solo CubiCasa cruda: tomaba openings de CubiCasa, walls de MitUNet, hacía re-anchor/filtros y luego permitía corrección humana. Hoy no tenemos esa capa intermedia.

## Chosen Approach

### 1. Backend: volver a un output annotation-first para openings

Para `ensemble`, el backend va a producir nuevamente `auto_annotations` de `door/window` basadas en el flujo legacy:

- CubiCasa propone openings
- MitUNet aporta walls
- backend re-anchor a la wall más cercana con filtro de distancia
- backend convierte openings a segmentos 2D de annotation

Desviación intencional respecto del flujo histórico:

- si una `door` viene sin `swing`, el backend completa un fallback automático para que el DXF no la descarte
- si una `window` necesita lado exterior, se completa desde la heurística actual

Eso mantiene la UX mínima pedida sin reabrir el picker viejo.

### 2. Frontend: revisión mínima session-only

El frontend va a cargar automáticamente esas `auto_annotations` en una capa de revisión encima de la imagen subida.

Reglas:

- solo se muestran `door` y `window`
- cada opening se puede seleccionar
- se puede arrastrar libremente
- se puede eliminar
- no se puede crear una nueva
- los cambios viven solo en memoria del componente

### 3. Flujo UX

1. Usuario sube imagen
2. Usuario dispara detección/revisión
3. El frontend recibe `structure + auto_annotations`
4. Se abre la vista de revisión sobre la imagen fuente
5. Si el usuario mueve o elimina openings, esas annotations de sesión pasan a ser la fuente para el próximo `generate-dxf`
6. El DXF se regenera con las annotations revisadas

## API Contract Changes

### Backend request

`GenerateStructureRequest` recupera un campo opcional:

- `annotations?: list[dict]`

Se usa solo como override session-only para openings revisadas por el usuario.

### Backend response

`ParseStructureResponse` y/o `GenerateStructureResponse` vuelven a exponer:

- `auto_annotations`

Pero limitadas a `door/window`, que son las únicas editables en esta iteración.

## Data Model

Las annotations de revisión mantienen el contrato viejo porque ya encaja con DXF y con la UI:

```ts
type OpeningAnnotation = {
  type: 'door' | 'window'
  x1: number
  y1: number
  x2: number
  y2: number
  swing?: 'up' | 'down' | 'left' | 'right'
  _source?: string
}
```

## Error Handling

- Si no hay openings detectadas, la UI no bloquea el flujo; simplemente no muestra elementos editables.
- Si el usuario borró todas las openings, el backend debe respetarlo y no reinyectar detecciones viejas en ese request.
- Si las annotations revisadas son inválidas, el backend cae al comportamiento actual y marca review flags claros.

## Testing Strategy

### Backend

- tests para restaurar `auto_annotations` desde ensemble
- tests para fallback automático de `door.swing`
- tests para `generate-dxf` usando annotations revisadas del request

### Frontend

- tests del hook/workflow para cargar `auto_annotations`
- tests del editor mínimo para borrar/mover annotations y serializarlas para el request

## Alternatives Considered

### A. Reabrir el editor completo viejo

**Pros:** reutiliza más código histórico.  
**Contras:** trae create/swing-picker/complexidad que el usuario NO pidió.

### B. Volver a CubiCasa directa sin capa de review

**Pros:** menos UI.  
**Contras:** repite exactamente el problema que ya vimos: output crudo poco confiable.

### C. Editor mínimo + backend legacy-style

**Elegida.**  
Es la mejor relación entre recall, velocidad de implementación y control humano.

## What to Learn Next

- Si la revisión mínima realmente mejora la calidad percibida
- Qué porcentaje de doors necesita corrección manual aun con fallback de swing
- Si vale la pena persistir annotations por proyecto en una segunda fase
