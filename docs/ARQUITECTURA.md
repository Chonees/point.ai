# Point.ai — Arquitectura Técnica Completa

**Preparado por:** Lucas Branchini
**Fecha:** Marzo 2026
**Version:** 1.0

---

## Contexto y Problema

Pointe Homes es una constructora residencial que maneja mas de 90 modelos de planos. El proceso actual de crear y adaptar documentos de construccion es completamente manual en AutoCAD, lo que genera un cuello de botella significativo en el equipo de diseno.

**El dolor especifico:**
- Crear un set completo de documentos de construccion desde cero toma dias
- Adaptar un plano existente a un terreno diferente toma horas de trabajo manual
- Generar variantes de fachada para el mismo plano requiere un dibujante dedicado

**El objetivo:**
Una interfaz web donde el equipo de Pointe Homes pueda generar y modificar planos de construccion completos en AutoCAD mediante lenguaje natural, en minutos en lugar de dias.

---

## Principios de Diseno

1. **Demo primero** — Cada sistema debe tener un entregable visible lo antes posible
2. **Un sistema a la vez** — No se empieza el siguiente hasta que el anterior funciona
3. **Capas como contrato** — Las capas estandar de Pointe Homes son la base de todo
4. **Sin intervencion humana** — El output debe ser un DWG listo para usar
5. **Aprendizaje continuo** — El sistema mejora con cada correccion del equipo

---

## Stack Tecnologico

| Capa | Tecnologia | Por que |
|------|-----------|---------|
| Frontend | React + TypeScript | Estandar profesional, facil de mantener |
| Backend | Python + FastAPI | Ecosistema CAD vive en Python |
| IA | Claude API (claude-sonnet-4-6) | Mejor razonamiento para geometria y reglas |
| Vision | Claude API Vision | Analizar imagenes de planos de entrada |
| AutoCAD | MCP Server (puran-water/autocad-mcp) | Control directo de AutoCAD LT 2024 via lenguaje natural |
| Lectura DWG | ezdxf (Python) | Lee y escribe DWG sin AutoCAD abierto |
| Base de datos | PostgreSQL | Guardar reglas, modelos, historial |
| Almacenamiento | AWS S3 | Archivos DWG generados |
| Infraestructura | Railway o Render | Deploy simple, bajo costo inicial |

---

## Como Funciona el MCP con AutoCAD

El MCP (Model Context Protocol) es el puente que conecta Claude directamente con AutoCAD LT 2024. En lugar de que una persona opere AutoCAD manualmente, Claude le da instrucciones al MCP y el MCP las ejecuta en AutoCAD en tiempo real.

```
Claude API
    ↓
MCP Server (autocad-mcp)
    ↓
AutoLISP Dispatcher (mcp_dispatch.lsp)
    ↓
AutoCAD LT 2024
    ↓
DWG generado / modificado
```

**El MCP expone 8 herramientas que Claude puede usar:**

| Herramienta | Funcion |
|-------------|---------|
| `drawing` | Abrir, guardar, exportar DWG |
| `entity` | Crear y modificar paredes, lineas, textos |
| `layer` | Gestionar capas |
| `block` | Insertar puertas, ventanas, bloques predefinidos |
| `annotation` | Cotas y dimensiones automaticas |
| `view` | Capturas del plano para preview |
| `system` | Ejecutar AutoLISP arbitrario |
| `pid` | Simbolos tecnicos (futuro uso en plomeria) |

---

## Codigos de Construccion

Todos los planos generados o modificados deben cumplir:

| Codigo | Aplica a |
|--------|----------|
| ICC - IRC 2021 | Todos los estados |
| ICC - NEC 2020 | Todos los estados (electrico) |
| ICC - IECC 2021 | Todos los estados (eficiencia energetica) |
| New Mexico Title 14 | Solo planos de Nuevo Mexico |

**Reglas minimas que el sistema nunca puede violar:**
- Cuartos minimo 10' x 10'
- Pasillos minimo 3'6" de ancho
- Marcos de puerta minimo 3'2" de ancho
- Setbacks segun municipio (variable por terreno)
- Ventilacion de atico minimo 1 SF por 150 SF de area

---

## Sistema 0 — Base de Extraccion DWG

> El cimiento de todo lo demas

### Que es

Un script Python que abre cualquier DWG de Pointe Homes y extrae toda su informacion estructurada en JSON.

### Por que primero

Sin entender que hay dentro de un DWG no se puede generar ni modificar nada. Este JSON es el contexto que le damos a Claude para que entienda que es un plano de Pointe Homes.

### Que extrae

```json
{
  "model": "Seminole 2000",
  "total_entities": 1847,
  "dimensions": {
    "width_ft": 37,
    "depth_ft": 54
  },
  "layers": {
    "WALLS": {
      "color": "white",
      "entities": 234,
      "elements": [
        {
          "type": "LINE",
          "start": [0, 0],
          "end": [37, 0],
          "length_ft": 37
        }
      ]
    },
    "DIMENSIONS": { "color": "cyan", "entities": 89 },
    "ELECTRICAL": { "color": "yellow", "entities": 156 },
    "TEXT": { "color": "white", "entities": 67 }
  },
  "rooms": [
    {
      "name": "MASTER BEDROOM",
      "width_ft": 14,
      "depth_ft": 12,
      "layer": "WALLS"
    }
  ],
  "doors": [],
  "windows": [],
  "building_codes_applied": ["IRC_2021", "NEC_2020", "IECC_2021"]
}
```

### Tecnologias
- `ezdxf` — lectura del DWG
- `Python` — procesamiento y extraccion
- `PostgreSQL` — almacenamiento del JSON extraido por modelo

### Senal de exito
El script corre sobre el DWG del Seminole 2000, extrae todas las capas, y el JSON resultante describe el plano con suficiente detalle para que Claude lo entienda sin ver el archivo original.

---

## Sistema 1 — Generacion de Plano desde Imagen

> El sistema mas urgente y el que mas impacto genera

### Que hace

Carlos ve un plano de un constructor nacional en internet que le gusto. Sube esa imagen a la interfaz web. El sistema genera ese plano completo en AutoCAD con las capas estandar de Pointe Homes, listo para usar.

### Por que es el primero

Es el caso de uso que mas tiempo ahorra. Hoy un dibujante tarda dias en reproducir un plano desde cero. Este sistema lo hace en minutos. Ademas, si el sistema puede generar un plano desde cero, puede tambien modificar uno existente — los Sistemas 2 y 3 son casos especiales de este mismo problema.

### Flujo completo

```
1. Carlos sube imagen del plano en la interfaz web
           ↓
2. Claude Vision analiza la imagen
   - Identifica cuartos y sus nombres
   - Extrae dimensiones aproximadas
   - Detecta puertas y ventanas
   - Mapea la distribucion general
           ↓
3. Claude aplica contexto de Pointe Homes
   - Carga el JSON del Sistema 0 como referencia
   - Ajusta medidas para cumplir codigos IRC/NEC/IECC
   - Asigna cada elemento a su capa correcta
   - Verifica reglas minimas (cuartos 10x10, pasillos 3'6")
           ↓
4. Claude genera instrucciones para AutoCAD via MCP
   - Crea las capas con los nombres estandar
   - Dibuja las paredes en capa WALLS
   - Inserta bloques de puertas y ventanas
   - Agrega dimensiones en capa DIMENSIONS
   - Agrega texto y notas en capa TEXT
   - Agrega electrico en capa ELECTRICAL
           ↓
5. AutoCAD ejecuta todas las instrucciones
           ↓
6. Sistema toma screenshot del resultado (herramienta view)
           ↓
7. Carlos ve preview en la interfaz web
           ↓
8. Carlos descarga el DWG completo
```

### Interfaz web — Lo que ve Carlos

```
┌─────────────────────────────────────┐
│  POINTE HOMES — GENERADOR DE PLANOS │
├─────────────────────────────────────┤
│                                     │
│  Subi la imagen del plano:          │
│  [ Arrastra o hace click aqui ]     │
│                                     │
│  Notas adicionales:                 │
│  [ Modificar la cocina, agregar     │
│    cuarto de estudio... ]           │
│                                     │
│  Estado: [ Texas ▼ ]               │
│                                     │
│  [ GENERAR PLANO ]                  │
│                                     │
├─────────────────────────────────────┤
│  Preview:          Descargar DWG    │
│  [ imagen del plano generado ]  [↓] │
└─────────────────────────────────────┘
```

### Tecnologias
- `React + TypeScript` — interfaz web
- `FastAPI` — backend que orquesta todo
- `Claude API Vision` — analisis de la imagen de entrada
- `Claude API` — razonamiento y generacion de instrucciones
- `MCP autocad-mcp` — ejecucion en AutoCAD LT 2024
- `ezdxf` — generacion headless como respaldo
- `AWS S3` — almacenamiento del DWG generado

### Senal de exito
Carlos sube una imagen de un plano de internet. El sistema genera un DWG en AutoCAD con las capas correctas de Pointe Homes que se parece al plano de la imagen. Renteria lo abre en AutoCAD y confirma que la estructura de capas es correcta.

---

## Sistema 2 — Adaptacion de Plano Existente al Terreno

### Que hace

Carlos tiene un terreno con dimensiones y setbacks especificos. Quiere saber si uno de sus 90 planos cabe. Si no cabe, el sistema ajusta el plano automaticamente respetando todas las restricciones internas.

### Por que despues del Sistema 1

Modificar un plano existente es un caso especial de generarlo. Si el Sistema 1 ya sabe como generar un plano con las capas correctas, el Sistema 2 agrega la logica de restricciones geometricas encima de eso.

### Flujo completo

```
1. Carlos ingresa dimensiones del terreno y setbacks del municipio
           ↓
2. Sistema verifica que planos de los 90 caben
   - Compara ancho y largo del plano vs area construible
   - Lista los que caben y los que no
           ↓
3. Si no cabe — Carlos elige cuanto ajustar
   "Necesito que el Seminole 2000 entre en este terreno"
           ↓
4. Claude calcula el plan de ajuste
   - Determina cuanto hay que quitar en total
   - Analiza que espacios pueden reducirse y cuales no
   - Distribuye el ajuste de forma inteligente
   - Verifica que nada quede por debajo del minimo de codigo
   - Presenta el plan antes de ejecutar:
     "Voy a quitarle 4" al living, 4" al pasillo principal
      y 4" al garage. Confirmas?"
           ↓
5. Carlos aprueba o ajusta el plan
           ↓
6. Sistema ejecuta los cambios en AutoCAD via MCP
   - Mueve las paredes afectadas
   - Reubica puertas si quedaron en posicion incorrecta
   - Actualiza todas las dimensiones automaticamente
   - Verifica que el resultado final cumpla los codigos
           ↓
7. Carlos ve preview y descarga el DWG modificado
```

### Logica de restricciones

```python
REGLAS_INAMOVIBLES = {
    "banos": "nunca reducir",
    "marcos_de_puerta": "minimo 3'2\"",
    "pasillos": "minimo 3'6\"",
    "cuartos": "minimo 10' x 10'",
    "garage": "minimo 20' x 20'"
}

REGLAS_FLEXIBLES = {
    "living": "puede reducirse hasta 15' x 15'",
    "comedor": "puede reducirse hasta 10' x 10'",
    "closets": "pueden reducirse hasta 4' x 4'",
    "garage": "puede reducirse si sigue siendo funcional"
}
```

### Tecnologias
- Todas las del Sistema 1
- `PostgreSQL` — reglas de restriccion por tipo de espacio
- Logica geometrica en `Python` — calculo de ajustes

### Senal de exito
Carlos ingresa las dimensiones de un terreno real donde el Seminole 2000 no cabe. El sistema calcula el ajuste, se lo muestra, Carlos aprueba, y el DWG modificado abre en AutoCAD con todas las dimensiones actualizadas correctamente.

---

## Sistema 3 — Generacion de Fachadas Nuevas

### Que hace

Un mismo plano puede tener multiples estilos de fachada. Carlos le dice que estilo quiere — contemporaneo, moderno, espanol, farmhouse — y el sistema genera esa fachada en AutoCAD, lista para usar.

### Por que ultimo

Las fachadas son el elemento mas visual y subjetivo. Requieren que los Sistemas 1 y 2 esten funcionando primero porque se generan sobre un plano base ya existente.

### Flujo completo

```
1. Carlos selecciona un plano base y describe el estilo de fachada
   "Quiero una fachada contemporanea para el Seminole 2000"
           ↓
2. Claude analiza el plano base
   - Lee las dimensiones del frente del plano
   - Identifica donde van ventanas y puertas
   - Entiende el ancho del garage
           ↓
3. Claude genera el diseno de fachada
   - Aplica el estilo solicitado
   - Respeta las aperturas existentes del plano
   - Genera 2-3 variantes para que Carlos elija
           ↓
4. Preview visual de las variantes
   (imagen generada con IA generativa)
           ↓
5. Carlos elige la variante que prefiere
           ↓
6. Sistema genera la elevacion en AutoCAD via MCP
   - Dibuja la fachada con las capas correctas
   - Agrega dimensiones y notas tecnicas
           ↓
7. Carlos descarga el DWG de la elevacion
```

### Estilos predefinidos

```
- Spanish / Mediterraneo
- Farmhouse
- Contemporaneo
- Moderno
- Tradicional
- Personalizado (descripcion libre)
```

### Tecnologias
- Todas las del Sistema 1
- `GPT-4o` o `DALL-E 3` — preview visual fotorrealista de la fachada
- `Claude API` — generacion de instrucciones tecnicas para AutoCAD

### Senal de exito
Carlos pide una fachada contemporanea para el Seminole 2000. El sistema genera 3 variantes visuales, Carlos elige una, y el DWG de la elevacion abre en AutoCAD con la estructura de capas correcta.

---

## Orden de Construccion

```
SEMANA 1-2: Sistema 0 — Extraccion DWG
├── Instalar ezdxf
├── Script de extraccion de capas
├── Generar JSON del Seminole 2000
└── Validar que Claude entiende el JSON

SEMANA 3-4: Sistema 1 — Generacion desde imagen (MVP)
├── Endpoint FastAPI que recibe imagen
├── Claude Vision analiza la imagen
├── Claude genera instrucciones AutoCAD
├── MCP ejecuta en AutoCAD
└── Preview + descarga DWG

SEMANA 5: Sistema 1 — Refinamiento
├── Mejorar precision de medidas
├── Agregar validacion de codigos
├── Mejorar interfaz web
└── Demo con Renteria y Carlos V

SEMANA 6-7: Sistema 2 — Adaptacion al terreno
├── Input de dimensiones de terreno
├── Logica de verificacion si cabe
├── Motor de calculo de ajustes
├── Confirmacion antes de ejecutar
└── Ejecucion en AutoCAD

SEMANA 8: Sistema 3 — Fachadas
├── Preview visual con IA generativa
├── Generacion de elevacion en AutoCAD
└── Variantes de estilo
```

---

## Costos Operativos Estimados (Mensual)

| Servicio | Uso estimado | Costo |
|----------|-------------|-------|
| Claude API | ~500 generaciones/mes | ~$50 |
| Railway / Render | Backend + DB | ~$20 |
| AWS S3 | Almacenamiento DWG | ~$5 |
| **Total** | | **~$75/mes** |

---

## Lo que se Necesita de Pointe Homes para Arrancar

| Entregable | Quien | Para que |
|------------|-------|----------|
| Login AutoCAD LT 2024 | Renteria | Instalar y conectar el MCP |
| DWG limpio con capas estandar | Renteria | Base del Sistema 0 |
| Lista de reglas minimas de diseno | Renteria | Motor de validacion de codigos |
| 2-3 imagenes de planos de prueba | Carlos V | Testear el Sistema 1 |

---

## Criterio de Exito Global

El sistema esta listo para produccion cuando Carlos puede:

1. **Subir una imagen de un plano** → recibir un DWG en AutoCAD en menos de 5 minutos
2. **Ingresar las dimensiones de un terreno** → saber que planos caben y recibir el ajuste automatico
3. **Pedir un estilo de fachada** → recibir la elevacion en AutoCAD lista para usar

Todo sin tocar AutoCAD manualmente.
