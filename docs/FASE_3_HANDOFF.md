# Fase 3 Handoff - Del Heuristico al Worker Real

## Lo que quedo resuelto en Fase 2

- `POST /api/v2/parse-structure` y `POST /api/v2/generate-dxf` ya aceptan `image`, `plan` o `structure`.
- Se agrego un adaptador de inferencia local en [`backend/inference_client.py`](../backend/inference_client.py).
- El backend `v2` ya soporta `image -> inferencia -> postproceso -> estructura canonica -> preview -> DXF`.
- Se agrego postproceso geometrico en [`backend/structure_postprocess.py`](../backend/structure_postprocess.py):
  - snap geometrico
  - merge de muros colineares
  - clasificacion exterior/interior
  - anclaje y filtrado de openings
- Se agrego almacenamiento de artefactos en [`backend/artifacts.py`](../backend/artifacts.py).
- `preview_url` y `artifact_urls` ya salen en las respuestas `v2`.

## Alcance real soportado hoy

El flujo de imagen de Fase 2 funciona para el alcance que se testeo:

- planos o mascaras simples con muros axis-aligned
- openings marcados con color
  - puerta: verde
  - ventana: azul
- geometria sin diagonales ni curvas
- muros representables por segmentos de 2 puntos

Eso esta probado y hoy pasa en CI local.

## Lo que NO esta resuelto todavia

- No hay worker GPU real.
- No hay modelo de segmentacion de floor plans.
- No hay soporte serio para planos reales con texto, muebles, cotas, ruido o geometria compleja.
- No hay junction graph `L/T/X`.
- No hay deteccion robusta de swing de puerta.
- No hay renderer de puertas `garage/sliding`.
- No hay metricas contra dataset real de Pointe.

## Testeo disponible al cerrar Fase 2

Se ejecuta con:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Estado esperado al cierre:

```text
7 passed
```

Cobertura actual:

- inferencia heuristica cruda desde imagen sintetica
- parseo legacy `rooms -> structure`
- parseo `raw structure -> canonical structure`
- API `parse-structure` por `plan`
- API `parse-structure` por `image`
- API `generate-dxf` por `plan`
- API `generate-dxf` por `image`
- descarga de preview y DXF

## Objetivo de la Fase 3

Reemplazar la inferencia heuristica local por una capa de inferencia estructural real que sirva planos Pointe reales.

## Trabajo recomendado en Fase 3

1. Crear cliente de worker remoto real.
   - mantener la interfaz `infer_structure(image_b64: str) -> dict`
   - agregar backend remoto por variable de entorno

2. Definir contrato del worker GPU.
   - input: imagen
   - output: masks / walls / openings / confidence / debug overlays
   - errores tipados

3. Integrar benchmark real.
   - dataset chico Pointe
   - guardar artefactos por corrida
   - comparar contra expected overlays o anotaciones

4. Mejorar postproceso.
   - junction graph
   - snap por interseccion
   - clasificacion exterior/interior mas robusta
   - openings solo si quedan anclados a muro valido

5. Extender renderer estructural.
   - `garage`
   - `sliding`
   - ventanas/puertas no ortogonales si el modelo las empieza a devolver

## Criterio tecnico para considerar Fase 3 terminada

No alcanza con que el endpoint responda.

Se deberia exigir:

- pruebas automatizadas sobre mocks del worker
- pruebas end-to-end sobre un subconjunto real de planos Pointe
- artefactos guardados por corrida
- comparacion visual o estructural reproducible
- threshold minimo definido para continuidad de muros y recall de openings

## Nota importante

La Fase 2 deja un pipeline correcto para el alcance soportado, pero no demuestra exito sobre planos reales de produccion. La Fase 3 tiene que cerrar exactamente esa brecha.
