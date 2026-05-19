# Opening Review Direct Manipulation Design

## Goal

Mantener el rollback del experimento automático de orientación, pero reemplazar la UX de botones por una revisión visual y directa: Opening Review debe mostrar el símbolo como saldrá en DXF y separar claramente **mover** de **orientar**.

## Scope

- Mantener el backend sin el experimento nuevo de orientación.
- Seguir usando `OpeningAnnotation.swing` como contrato de review.
- Dibujar puertas y ventanas con una geometría DXF-like en la capa de review.
- Hacer que el click sobre la opening solo seleccione.
- Hacer que el movimiento ocurra únicamente desde un handle central visible.
- Hacer que la orientación ocurra desde targets visuales sobre el símbolo, no desde botones externos.
- No reintroducir control de bisagra en esta iteración.

## Product Loop + Architecture

- **Product loop:** Loop 1 / floor plan curation.
- **Layers touched:**
  - **Desktop UI:** `frontend/src/features/workspace/OpeningsReviewCanvas.tsx`
  - **Desktop helpers:** `frontend/src/features/workspace/openingsReview.ts`
  - **Contracts:** sin cambios; se sigue usando `OpeningAnnotation.swing`

## Chosen Approach

### 1. Render DXF-like dentro del review

La review ya no muestra solamente un segmento con letras D/W. Ahora usa la misma lógica visual base del renderer viejo:

- **door** -> dos líneas de hoja + arco
- **window** -> líneas paralelas + end caps + sill/exterior line

Eso hace que la preview tenga la misma intención visual que el DXF final.

### 2. Separar intenciones de interacción

La UX nueva define tres zonas claras:

- **click sobre la opening** -> seleccionar
- **drag del handle central** -> mover
- **click sobre los targets de orientación** -> elegir lado/dirección

La interacción deja de ser ambigua porque ya no existe un mismo gesto para seleccionar y mover al mismo tiempo.

### 3. Mostrar las opciones sobre el propio símbolo

Cuando una opening está seleccionada:

- aparece un **handle central** para mover
- aparecen los **targets de dirección** en los lados válidos según orientación
- se dibujan las variantes de preview sobre la propia opening

Así la persona no traduce una lista de botones a una geometría mental: toca directamente el dibujo.

## Testing Strategy

- **Helpers:** geometría DXF-like para door/window, centro de move-handle, targets de swing.
- **Component:** selección sin mover, cambio de swing desde target visual, movimiento solo desde el handle central.
- **Frontend workflow:** mantener verdes los tests del request session-only (`useGenerateDxf`).

## Alternatives Considered

### A. Mantener botones de dirección

**Pros:** implementación mínima.  
**Contras:** UX rechazada explícitamente por el usuario.

### B. Hacer drag libre sobre cualquier parte del símbolo

**Pros:** menos elementos visuales.  
**Contras:** vuelve a mezclar mover con orientar y reintroduce ambigüedad.

### C. Direct manipulation con handle central + targets de swing

**Elegida.**  
Es la forma más simple de dejar una intención por gesto y mantener la review visualmente alineada con el DXF.
