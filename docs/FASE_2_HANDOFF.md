# Fase 2 Handoff - Estructura Real

## Lo que ya quedo implementado en Fase 1

- Se agrego un contrato `v2` basado en `walls[]`, `openings[]` y `structure_meta`.
- Se creo [`backend/plan_parser.py`](../backend/plan_parser.py) como parser canonico.
- El parser soporta dos entradas:
  - `plan` legacy basado en `rooms[]`
  - `structure` directa para el pipeline nuevo
- Se creo [`backend/structural_generator.py`](../backend/structural_generator.py) para generar DXF desde estructura canonica.
- Se agregaron endpoints nuevos:
  - `POST /api/v2/parse-structure`
  - `POST /api/v2/generate-dxf`
- El pipeline legacy (`/api/generate`) sigue intacto.

## Que resuelve esta fase

- El backend nuevo ya no depende de `rooms[]` como contrato interno.
- Ya existe un punto de entrada estable para que una futura inferencia estructural entregue `walls/openings`.
- Ya existe un renderer DXF separado del orquestador legacy.

## Limitaciones actuales

- Todavia no hay servicio de inferencia GPU.
- Todavia no hay procesamiento real de imagen -> estructura.
- `preview_url` se devuelve como `null`.
- El renderer `v2` de Fase 1 soporta solo muros axis-aligned de 2 puntos.
- Puertas `garage` y `sliding` hoy quedan como gap de muro sin simbolo especializado.
- No hay wall graph, junction classification ni confidence heuristics avanzadas.

## Objetivo de la Fase 2

Conectar el backend `v2` a una capa real de inferencia/parseo estructural para dejar de depender del adaptador `legacy_rooms_adapter`.

## Alcance recomendado para Fase 2

1. Crear un adaptador de inferencia desacoplado.
   - Archivo sugerido: `backend/inference_client.py`
   - Funcion sugerida: `infer_structure(image_b64: str) -> dict`
   - Por ahora puede ser mockeable aunque no exista aun el worker GPU.

2. Extender `POST /api/v2/parse-structure`.
   - Aceptar `image`
   - Si viene `image`, llamar a `infer_structure()`
   - Convertir la salida del modelo al contrato canonico del parser

3. Agregar postproceso estructural.
   - snap ortogonal
   - merge de colineares
   - filtros de openings invalidos
   - clasificacion exterior/interior con confidence

4. Empezar artefactos de debug.
   - `preview_url`
   - overlays de walls/openings
   - guardar JSON canonico por corrida

5. Preparar el contrato para worker GPU externo.
   - input: imagen base64
   - output: masks/polylines/openings/confidence
   - errores tipados

## Archivos clave para seguir

- [`backend/plan_parser.py`](../backend/plan_parser.py)
- [`backend/structural_generator.py`](../backend/structural_generator.py)
- [`backend/app.py`](../backend/app.py)
- [`backend/models.py`](../backend/models.py)

## Nota de estrategia

La Fase 2 ya no deberia invertir tiempo en mejorar prompts o reglas de Claude para geometria. La pieza que falta ahora es reemplazar la fuente de estructura, no seguir refinando el contrato viejo.
