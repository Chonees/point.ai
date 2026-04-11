/**
 * Interior Realistic furniture catalog — 1,579 GLB models + color palette
 * Models from ithappy studios "Interior Realistic" pack
 */

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface FurnitureItem {
  id: string
  name: string
  category: string      // UI group
  subcategory: string   // raw file prefix (armchair, sofa, etc.)
  glb: string           // path relative to /models/
  scale: number
  wallMount?: boolean   // true = flat panel that needs to be rotated upright when placed
}

export interface PaletteColor {
  hex: string
  row: number
  col: number
}

export interface MaterialPreset {
  id: string
  name: string
  category: 'floor' | 'wall'
  color: string
  roughness: number
}

/* ------------------------------------------------------------------ */
/*  Category mapping: raw file prefix → UI group                       */
/* ------------------------------------------------------------------ */

const CATEGORY_MAP: Record<string, string> = {
  // Seating
  armchair: 'Seating',
  lounge_chair: 'Seating',
  office_chair: 'Seating',
  kitchen_chair: 'Seating',
  sofa: 'Seating',
  ottoman: 'Seating',
  // Tables
  coffee_table: 'Tables',
  kitchen_table: 'Tables',
  office_table: 'Tables',
  // Bedroom
  bed: 'Bedroom',
  closet: 'Bedroom',
  carpet: 'Bedroom',
  // Storage
  shelf: 'Storage',
  clothes: 'Storage',
  // Kitchen & Bath
  kitchen_item: 'Kitchen & Bath',
  bathroom_item: 'Kitchen & Bath',
  // Lighting & Decor
  lamp: 'Decor',
  flower: 'Decor',
  picture: 'Decor',
  Curtains: 'Decor',
  // Electronics
  electronics: 'Electronics',
  entertainment: 'Electronics',
  tv_wall: 'Electronics',
  musical_instrument: 'Electronics',
  // Structure
  door: 'Structure',
  window: 'Structure',
  wall: 'Structure',
  Walls: 'Structure',
  Partitions: 'Structure',
  Stairs: 'Structure',
  floor: 'Structure',
  // Kids & Gym
  for_kids: 'Kids & Gym',
  toy: 'Kids & Gym',
  training_item: 'Kids & Gym',
  // Props
  prop: 'Props',
  shop: 'Props',
  warehouse: 'Props',
}

/** Humanize a raw category name: "bathroom_item" → "Bathroom Item" */
function humanize(raw: string): string {
  return raw
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bTv\b/, 'TV')
}

/* ------------------------------------------------------------------ */
/*  Model manifest — compact [prefix, count] pairs                     */
/*  Expands to full FurnitureItem[] at module load                     */
/* ------------------------------------------------------------------ */

// [prefix, count, wallMount?] — wallMount=true for flat panels that need upright rotation
const MODEL_COUNTS: [string, number, boolean?][] = [
  ['armchair', 20],
  ['bathroom_item', 40],
  ['bed', 17],
  ['carpet', 21],
  ['closet', 38],
  ['clothes', 42],
  ['coffee_table', 23],
  ['Curtains', 29],
  ['door', 26],
  ['electronics', 38],
  ['entertainment', 30],
  ['floor', 18],
  ['flower', 37],
  ['for_kids', 7],
  ['kitchen_chair', 38],
  ['kitchen_item', 65],
  ['kitchen_table', 20],
  ['lamp', 33],
  ['lounge_chair', 20],
  ['musical_instrument', 19],
  ['office_chair', 22],
  ['office_table', 40],
  ['ottoman', 16],
  ['Partitions', 117],
  ['picture', 66],
  ['prop', 104],
  ['shelf', 73],
  ['shop', 99],
  ['sofa', 30],
  ['Stairs', 105],
  ['toy', 37],
  ['training_item', 27],
  ['tv_wall', 25],
  ['wall', 18, true],  // flat panels — need upright rotation
  ['Walls', 143],
  ['warehouse', 39],
  ['window', 37],
]

/** Default scale for all interior models (calibrate after first load) */
const DEFAULT_SCALE = 40

export const FURNITURE: FurnitureItem[] = MODEL_COUNTS.flatMap(
  ([prefix, count, isWallMount]) => {
    const category = CATEGORY_MAP[prefix] ?? 'Other'
    const label = humanize(prefix)
    const items: FurnitureItem[] = []

    for (let i = 1; i <= count; i++) {
      const num = String(i).padStart(3, '0')
      items.push({
        id: `${prefix}_${num}`,
        name: `${label} ${i}`,
        category,
        subcategory: prefix,
        glb: `interior/${prefix}_${num}.glb`,
        scale: DEFAULT_SCALE,
        ...(isWallMount && { wallMount: true }),
      })
    }

    return items
  },
)

/* ------------------------------------------------------------------ */
/*  Categories & subcategories                                         */
/* ------------------------------------------------------------------ */

/** Ordered UI categories */
export const CATEGORIES = [
  'Seating',
  'Tables',
  'Bedroom',
  'Storage',
  'Kitchen & Bath',
  'Decor',
  'Electronics',
  'Structure',
  'Kids & Gym',
  'Props',
]

/** All unique subcategories (raw prefixes) */
export const SUBCATEGORIES = [...new Set(FURNITURE.map((f) => f.subcategory))]

/** Get subcategories within a UI category */
export function getSubcategories(category: string): string[] {
  return [
    ...new Set(
      FURNITURE.filter((f) => f.category === category).map((f) => f.subcategory),
    ),
  ]
}

/* ------------------------------------------------------------------ */
/*  Color palette — extracted from Textures.png (9 cols × 8 rows)      */
/* ------------------------------------------------------------------ */

const PALETTE_GRID: string[][] = [
  ['#620c0c', '#4a0b2b', '#072657', '#003436', '#0f3311', '#85450c', '#671d06', '#121212', '#151b1e'],
  ['#c62828', '#ad1a56', '#1266c1', '#00838f', '#2e7d32', '#f9a826', '#d84314', '#424242', '#37474f'],
  ['#d32f2f', '#c21f5b', '#1876d2', '#0097a7', '#378e3b', '#fbc02b', '#e64a18', '#616161', '#445a64'],
  ['#e53935', '#d82360', '#1a87e5', '#00acc1', '#42a047', '#fdd835', '#f44e19', '#757575', '#546e7a'],
  ['#ef5350', '#ec407a', '#42a5f5', '#26c6da', '#65bb6a', '#ffee58', '#ff7041', '#bdbdbd', '#78909c'],
  ['#e57373', '#f06292', '#64b5f6', '#4dd0e1', '#80c784', '#fff172', '#ff8a65', '#e0e0e0', '#90a4ae'],
  ['#ef9a9a', '#f48fb1', '#90caf9', '#80deea', '#a5d6a7', '#fff59e', '#ffab91', '#eeeeee', '#b0bec5'],
  ['#ffebee', '#fce4ec', '#e3f2fd', '#e0f7fa', '#e8f5e9', '#fffde7', '#fbe9e7', '#fafafa', '#eceff1'],
]

export const COLOR_PALETTE: PaletteColor[] = PALETTE_GRID.flatMap(
  (row, rowIdx) => row.map((hex, colIdx) => ({ hex, row: rowIdx, col: colIdx })),
)

/** Column labels for the palette */
export const PALETTE_COLUMNS = [
  'Red', 'Pink', 'Blue', 'Cyan', 'Green', 'Yellow', 'Orange', 'Gray', 'Blue Gray',
]

/* ------------------------------------------------------------------ */
/*  Material presets (floor & wall)                                    */
/* ------------------------------------------------------------------ */

export const MATERIALS: MaterialPreset[] = [
  { id: 'hardwood', name: 'Hardwood', category: 'floor', color: '#8B6914', roughness: 0.6 },
  { id: 'oak', name: 'Oak', category: 'floor', color: '#C4A265', roughness: 0.55 },
  { id: 'walnut', name: 'Walnut', category: 'floor', color: '#5C3317', roughness: 0.6 },
  { id: 'tile-white', name: 'White Tile', category: 'floor', color: '#F0EDE8', roughness: 0.3 },
  { id: 'tile-gray', name: 'Gray Tile', category: 'floor', color: '#9E9E9E', roughness: 0.35 },
  { id: 'marble', name: 'Marble', category: 'floor', color: '#E8E0D8', roughness: 0.15 },
  { id: 'carpet-beige', name: 'Beige Carpet', category: 'floor', color: '#C8B896', roughness: 0.95 },
  { id: 'concrete', name: 'Concrete', category: 'floor', color: '#A0A0A0', roughness: 0.8 },
  { id: 'white-paint', name: 'White Paint', category: 'wall', color: '#F5F5F0', roughness: 0.9 },
  { id: 'cream-paint', name: 'Cream', category: 'wall', color: '#F5F0E0', roughness: 0.9 },
  { id: 'gray-paint', name: 'Light Gray', category: 'wall', color: '#D0D0D0', roughness: 0.9 },
  { id: 'warm-gray', name: 'Warm Gray', category: 'wall', color: '#C8BEB0', roughness: 0.9 },
  { id: 'sage', name: 'Sage', category: 'wall', color: '#B2BDA0', roughness: 0.9 },
  { id: 'navy', name: 'Navy', category: 'wall', color: '#2C3E50', roughness: 0.85 },
]
