# Arquitectura Point.ai (Actualizada 2026-03-12)

**Empresa:** Pointe Homes
**Version:** 3.0

---

## Estructura del Proyecto

```
Point.ai/
├── .env                         # ANTHROPIC_API_KEY (gitignored)
├── .env.example                 # Template
├── .mcp.json                    # Config MCP (AutoCAD)
├── start-backend.bat/.sh        # Iniciar backend
├── start-frontend.bat/.sh       # Iniciar frontend
│
├── backend/
│   ├── __init__.py              # Package marker
│   ├── app.py                   # FastAPI server — solo rutas (~90 lineas)
│   ├── models.py                # Pydantic request/response models
│   ├── prompts.py               # System prompt + analyze prompt para Claude
│   ├── claude.py                # Logica Claude API (analyze_image, generate_plan)
│   ├── validation.py            # Validacion post-AI (door/window fixes)
│   ├── generator.py             # JSON → DXF orchestrator
│   ├── extract_floorplan.py     # Extractor de DXF existentes
│   ├── components/
│   │   ├── __init__.py          # Re-exports
│   │   ├── primitives.py        # Wrappers ezdxf (add_line, add_arc, add_text)
│   │   ├── layers.py            # 15 layers Pointe Homes + setup_doc()
│   │   ├── walls.py             # Paredes: collect, dedup, merge, draw
│   │   ├── doors.py             # Puertas: draw_door, draw_doors_for_room
│   │   ├── windows.py           # Ventanas: draw_window_h/v, draw_windows_for_room
│   │   └── labels.py            # Labels: draw_label
│   └── data/
│       └── plans/               # DWGs/DXFs originales de modelos
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # UI principal (React)
│   │   ├── main.tsx             # Entry point
│   │   └── index.css            # Tailwind v4
│   ├── dist/                    # Build produccion (gitignored)
│   ├── vite.config.ts           # Vite + Tailwind + proxy a backend
│   ├── package.json
│   └── tsconfig.json
│
└── docs/                        # Documentacion
    ├── ARQUITECTURA_ACTUAL_2026-03-12.md  # Este archivo
    ├── ARQUITECTURA.md
    └── arquitectura_sistema1.md
```

---

## Modulos Backend

El backend esta modularizado en 6 archivos con responsabilidades claras:

| Modulo | Responsabilidad |
|--------|----------------|
| `app.py` | FastAPI setup, CORS, rutas HTTP (~90 lineas) |
| `models.py` | Pydantic schemas: AnalyzeRequest, GenerateRequest, etc. |
| `prompts.py` | SYSTEM_PROMPT (reglas para Claude) + ANALYZE_PROMPT (vision) |
| `claude.py` | Llamadas a Claude API: `analyze_image()`, `generate_plan()`, `parse_image_data()` |
| `validation.py` | Post-procesamiento: `validate_plan()` corrige errores de doors/windows |
| `generator.py` | Orchestrador JSON → DXF usando components/ |

### Flujo de dependencias

```
app.py
  ├── models.py        (request/response types)
  ├── claude.py         (AI calls)
  │     └── prompts.py  (system prompts)
  ├── validation.py     (plan fixing)
  └── generator.py      (DXF generation)
        └── components/  (ezdxf primitives)
```

---

## Flujo General

```
Usuario escribe prompt en el browser
        │
   React App (frontend :5173)
        │ POST /api/generate {prompt, image?}
   FastAPI (backend :8000)
        │
   app.py → claude.py (llama Claude API claude-sonnet-4-6)
        │
   Claude devuelve JSON (floor plan)
        │
   app.py → validation.py (corrige doors/windows)
        │
   app.py → generator.py → components/
        │
   Archivo .dxf guardado en disco
        │ GET /downloads/xxx.dxf
   Usuario descarga el DXF → abre en AutoCAD
```

---

## Endpoints

| Endpoint | Metodo | Descripcion |
|----------|--------|-------------|
| `/` | GET | Sirve React build (frontend/dist/index.html) |
| `/api/analyze` | POST | Imagen → Claude Vision → descripcion texto |
| `/api/generate` | POST | Prompt → Claude → JSON → validacion → DXF |
| `/downloads/{file}` | GET | Descarga DXF generado |

### POST /api/analyze
1. Recibe `{image}` (base64)
2. `claude.py → analyze_image()` envia a Claude Vision
3. Retorna `{description}` — texto descriptivo del floor plan

### POST /api/generate
1. Recibe `{prompt, image?}` (image = base64 opcional)
2. `claude.py → generate_plan()` llama Claude con SYSTEM_PROMPT
3. `validation.py → validate_plan()` corrige errores comunes
4. `generator.py → generate()` crea DXF
5. Retorna `{dxf_url, plan}`

---

## Validacion de Planos (`validation.py`)

Post-procesamiento automatico del JSON de Claude para corregir errores comunes:

| Regla | Que hace |
|-------|----------|
| No windows en interiores | Rooms como BATH, CLOSET, HALL nunca tienen ventanas |
| Interior wall fix | Ventana en pared compartida entre rooms → se convierte en puerta |
| Door guarantee | Si un room no tiene puerta, agrega una en la primera pared interior |

Detecta paredes interiores comparando coordenadas de rooms adyacentes (tolerancia 5").

---

## Como correr

### Desarrollo (2 terminales)

**Terminal 1 — Backend:**
```bash
start-backend.bat        # Windows
./start-backend.sh       # Linux/Mac
# o manual: .venv/Scripts/uvicorn backend.app:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
start-frontend.bat       # Windows
./start-frontend.sh      # Linux/Mac
# o manual: cd frontend && npm run dev
```

Frontend corre en `localhost:5173` con proxy automatico al backend en `:8000`.

### Produccion (1 terminal)
```bash
cd frontend && npx vite build    # genera frontend/dist/
uvicorn backend.app:app          # sirve todo desde :8000
```

**Variables de entorno:** `.env` en la raiz con `ANTHROPIC_API_KEY`. Cargado via `python-dotenv`.

---

## Frontend — React + Tailwind + Framer Motion

Stack: Vite + React + TypeScript + Tailwind CSS v4 + Framer Motion

**Estilo:** Minimalista negro/gris (#09090b fondo, zinc grays, sin colores brillantes)

**Funcionalidad:**
- Titulo "Pointe.ai" con subtitulo "Floor Plan Generator"
- Textarea para describir el floor plan
- Upload de imagen con auto-analisis via Claude Vision
- Boton Generate con spinner animado
- Resultado: Download DXF + JSON preview colapsable

**Config Vite (`vite.config.ts`):**
- Proxy `/api` y `/downloads` → `localhost:8000`
- Build output → `frontend/dist/`

---

## Convenios CAD Pointe Homes

| Parametro | Valor |
|-----------|-------|
| Unidades | 1 unit = 1 inch |
| Wall thickness | 4 inches |
| Door slab | 1.5 inches |
| Door swing | 90 grados |
| Room label height | 9 inches |
| DXF format | R2018 |

### Layers principales

| Layer | Color | Uso |
|-------|-------|-----|
| WALLS | 7 (blanco) | Paredes |
| DOORS | 157 (violeta) | Puertas |
| WINS | 121 (verde) | Ventanas |
| ROOM LBLS | 253 (gris) | Nombres de cuartos |
| DIMS | 137 | Dimensiones |

---

## JSON Schema de entrada

```json
{
  "model": "nombre del plano",
  "rooms": [
    {
      "name": "ROOM NAME",
      "x": 0, "y": 0, "w": 300, "h": 200,
      "doors": [
        {"wall": "bottom", "offset": 20, "width": 36, "type": "normal"}
      ],
      "windows": [
        {"wall": "top", "offset": 60, "width": 48}
      ]
    }
  ]
}
```

### Reglas de Doors vs Windows (en SYSTEM_PROMPT)
- **Doors:** Conectan rooms entre si, al hallway, o al exterior
- **Windows:** SOLO en paredes exteriores (no compartidas con otro room)
- Bathrooms, closets, laundry: solo puerta, sin ventanas
- Garage: puerta garage exterior + puerta normal al interior
- Lanai/Patio: puerta sliding desde living, sin ventanas
- Cada room debe tener al menos una puerta
