/** Furniture catalog — ArchViz Realistic (Unreal) + Kenney (fallback) */

export interface FurnitureItem {
  id: string
  name: string
  category: string
  glb: string      // path relative to /models/
  scale: number
  icon: string
}

export interface MaterialPreset {
  id: string
  name: string
  category: 'floor' | 'wall'
  color: string
  roughness: number
}

// ArchViz realistic models (from Unreal ArchVisRT pack, converted to GLB)
// Scale ~0.4 (Unreal units cm → our units ~inches, 1:2.54 ≈ 0.4)
const AV = 'archviz/'
const AVS = 0.4

export const FURNITURE: FurnitureItem[] = [
  // Living Room
  { id: 'av-couch', name: 'Couch', category: 'Living', glb: `${AV}SM_Couch.glb`, scale: AVS, icon: '🛋' },
  { id: 'av-livingchair', name: 'Armchair', category: 'Living', glb: `${AV}SM_LivingRoomChair.glb`, scale: AVS, icon: '🪑' },
  { id: 'av-coffeetable', name: 'Coffee Table', category: 'Living', glb: `${AV}SM_CoffeeTable.glb`, scale: AVS, icon: '🪵' },
  { id: 'av-sidetable', name: 'Side Table', category: 'Living', glb: `${AV}SM_SideTable.glb`, scale: AVS, icon: '🪵' },
  { id: 'av-sidetable1', name: 'Side Table 2', category: 'Living', glb: `${AV}SM_SideTable_01.glb`, scale: AVS, icon: '🪵' },
  { id: 'av-sidetable2', name: 'Side Table 3', category: 'Living', glb: `${AV}SM_SideTable_02.glb`, scale: AVS, icon: '🪵' },
  { id: 'av-tv', name: 'TV', category: 'Living', glb: `${AV}SM_TV.glb`, scale: AVS, icon: '📺' },
  { id: 'av-tvstand', name: 'TV Stand', category: 'Living', glb: `${AV}SM_TVStand.glb`, scale: AVS, icon: '📺' },
  { id: 'av-tvshelf-l', name: 'TV Shelf Large', category: 'Living', glb: `${AV}SM_TVStandShelf_Large.glb`, scale: AVS, icon: '📺' },
  { id: 'av-tvshelf-s', name: 'TV Shelf Small', category: 'Living', glb: `${AV}SM_TVStandShelf_Small.glb`, scale: AVS, icon: '📺' },
  { id: 'av-rug', name: 'Rug', category: 'Living', glb: `${AV}SM_Rug_01.glb`, scale: AVS, icon: '🟫' },
  { id: 'av-curtainback', name: 'Curtain Back', category: 'Living', glb: `${AV}SM_CurtainBack.glb`, scale: AVS, icon: '🪟' },
  { id: 'av-curtainfront', name: 'Curtain Front', category: 'Living', glb: `${AV}SM_CurtainFront.glb`, scale: AVS, icon: '🪟' },
  { id: 'av-radiator', name: 'Radiator', category: 'Living', glb: `${AV}SM_Radiator.glb`, scale: AVS, icon: '🔥' },

  // Dining
  { id: 'av-diningtable', name: 'Dining Table', category: 'Dining', glb: `${AV}SM_DiningTable.glb`, scale: AVS, icon: '🪑' },
  { id: 'av-diningchair', name: 'Dining Chair', category: 'Dining', glb: `${AV}SM_DiningChair_01.glb`, scale: AVS, icon: '🪑' },
  { id: 'av-diningrug', name: 'Dining Rug', category: 'Dining', glb: `${AV}SM_DiningRoomRug.glb`, scale: AVS, icon: '🟫' },

  // Shelves & Storage
  { id: 'av-shelf', name: 'Shelf', category: 'Storage', glb: `${AV}SM_Shelf.glb`, scale: AVS, icon: '📚' },
  { id: 'av-laddershelf', name: 'Ladder Shelf', category: 'Storage', glb: `${AV}SM_LadderShelf.glb`, scale: AVS, icon: '📚' },
  { id: 'av-sidetableshelf', name: 'Shelf Table', category: 'Storage', glb: `${AV}SM_SideTableShelf.glb`, scale: AVS, icon: '📚' },
  { id: 'av-basket', name: 'Basket', category: 'Storage', glb: `${AV}SM_Basket.glb`, scale: AVS, icon: '🧺' },
  { id: 'av-box', name: 'Box', category: 'Storage', glb: `${AV}SM_Box_01.glb`, scale: AVS, icon: '📦' },
  { id: 'av-coatrack', name: 'Coat Rack', category: 'Storage', glb: `${AV}SM_CoatRack.glb`, scale: AVS, icon: '🧥' },

  // Lighting
  { id: 'av-standinglamp', name: 'Standing Lamp', category: 'Lighting', glb: `${AV}SM_StandingLamp.glb`, scale: AVS, icon: '💡' },
  { id: 'av-hanginglight', name: 'Hanging Light', category: 'Lighting', glb: `${AV}SM_HangingLight.glb`, scale: AVS, icon: '💡' },
  { id: 'av-candle', name: 'Candle', category: 'Lighting', glb: `${AV}SM_Candle.glb`, scale: AVS, icon: '🕯' },
  { id: 'av-candlestick', name: 'Candlestick', category: 'Lighting', glb: `${AV}SM_CandleStick.glb`, scale: AVS, icon: '🕯' },

  // Decor
  { id: 'av-pillow1', name: 'Pillow', category: 'Decor', glb: `${AV}SM_Pillow_01.glb`, scale: AVS, icon: '🛏' },
  { id: 'av-pillow2', name: 'Pillow 2', category: 'Decor', glb: `${AV}SM_Pillow_02.glb`, scale: AVS, icon: '🛏' },
  { id: 'av-blanket1', name: 'Throw Blanket', category: 'Decor', glb: `${AV}SM_ThrowBlanket_01.glb`, scale: AVS, icon: '🧣' },
  { id: 'av-blanket2', name: 'Throw Blanket 2', category: 'Decor', glb: `${AV}SM_ThrowBlanket_02.glb`, scale: AVS, icon: '🧣' },
  { id: 'av-vase1', name: 'Vase', category: 'Decor', glb: `${AV}SM_Vase_01.glb`, scale: AVS, icon: '🏺' },
  { id: 'av-vase2', name: 'Vase 2', category: 'Decor', glb: `${AV}SM_Vase_02.glb`, scale: AVS, icon: '🏺' },
  { id: 'av-vase3', name: 'Vase 3', category: 'Decor', glb: `${AV}SM_Vase_03.glb`, scale: AVS, icon: '🏺' },
  { id: 'av-bowl', name: 'Bowl', category: 'Decor', glb: `${AV}SM_Bowl_01.glb`, scale: AVS, icon: '🥣' },
  { id: 'av-tray', name: 'Tray', category: 'Decor', glb: `${AV}SM_Tray.glb`, scale: AVS, icon: '🍽' },
  { id: 'av-frame1', name: 'Frame', category: 'Decor', glb: `${AV}SM_Frame_01.glb`, scale: AVS, icon: '🖼' },
  { id: 'av-picture1', name: 'Picture', category: 'Decor', glb: `${AV}SM_Picture_01.glb`, scale: AVS, icon: '🖼' },
  { id: 'av-picture2', name: 'Picture 2', category: 'Decor', glb: `${AV}SM_Picture_02.glb`, scale: AVS, icon: '🖼' },
  { id: 'av-book1', name: 'Books', category: 'Decor', glb: `${AV}SM_Book_01.glb`, scale: AVS, icon: '📚' },
  { id: 'av-book2', name: 'Books 2', category: 'Decor', glb: `${AV}SM_Book_02.glb`, scale: AVS, icon: '📚' },
  { id: 'av-apple', name: 'Apple', category: 'Decor', glb: `${AV}SM_Apple.glb`, scale: AVS, icon: '🍎' },
  { id: 'av-newspaper', name: 'Newspaper', category: 'Decor', glb: `${AV}SM_Newspaper.glb`, scale: AVS, icon: '📰' },
  { id: 'av-glass', name: 'Glass', category: 'Decor', glb: `${AV}SM_Glass_01.glb`, scale: AVS, icon: '🥃' },

  // Plants
  { id: 'av-aglaonema', name: 'Aglaonema', category: 'Plants', glb: `${AV}SM_Aglaonema_01.glb`, scale: AVS, icon: '🌿' },
  { id: 'av-amaryllis', name: 'Amaryllis', category: 'Plants', glb: `${AV}SM_Amaryllis_01.glb`, scale: AVS, icon: '🌺' },
  { id: 'av-dracaena', name: 'Dracaena', category: 'Plants', glb: `${AV}SM_Dracaena_01.glb`, scale: AVS, icon: '🌴' },
  { id: 'av-snake', name: 'Snake Plant', category: 'Plants', glb: `${AV}SM_SnakePlant_01.glb`, scale: AVS, icon: '🪴' },
  { id: 'av-hedra', name: 'Ivy', category: 'Plants', glb: `${AV}SM_Hedra_01.glb`, scale: AVS, icon: '🌱' },
  { id: 'av-chloro', name: 'Spider Plant', category: 'Plants', glb: `${AV}SM_Chlorophytum_01.glb`, scale: AVS, icon: '🌿' },
  { id: 'av-pot3', name: 'Pot', category: 'Plants', glb: `${AV}SM_Pot_03.glb`, scale: AVS, icon: '🪴' },
  { id: 'av-pot4', name: 'Pot 2', category: 'Plants', glb: `${AV}SM_Pot_04.glb`, scale: AVS, icon: '🪴' },
  { id: 'av-potstand', name: 'Pot Stand', category: 'Plants', glb: `${AV}SM_PotStand_01.glb`, scale: AVS, icon: '🪴' },
]

export const MATERIALS: MaterialPreset[] = [
  // Floors
  { id: 'hardwood', name: 'Hardwood', category: 'floor', color: '#8B6914', roughness: 0.6 },
  { id: 'oak', name: 'Oak', category: 'floor', color: '#C4A265', roughness: 0.55 },
  { id: 'walnut', name: 'Walnut', category: 'floor', color: '#5C3317', roughness: 0.6 },
  { id: 'tile-white', name: 'White Tile', category: 'floor', color: '#F0EDE8', roughness: 0.3 },
  { id: 'tile-gray', name: 'Gray Tile', category: 'floor', color: '#9E9E9E', roughness: 0.35 },
  { id: 'marble', name: 'Marble', category: 'floor', color: '#E8E0D8', roughness: 0.15 },
  { id: 'carpet-beige', name: 'Beige Carpet', category: 'floor', color: '#C8B896', roughness: 0.95 },
  { id: 'concrete', name: 'Concrete', category: 'floor', color: '#A0A0A0', roughness: 0.8 },
  // Walls
  { id: 'white-paint', name: 'White Paint', category: 'wall', color: '#F5F5F0', roughness: 0.9 },
  { id: 'cream-paint', name: 'Cream', category: 'wall', color: '#F5F0E0', roughness: 0.9 },
  { id: 'gray-paint', name: 'Light Gray', category: 'wall', color: '#D0D0D0', roughness: 0.9 },
  { id: 'warm-gray', name: 'Warm Gray', category: 'wall', color: '#C8BEB0', roughness: 0.9 },
  { id: 'sage', name: 'Sage', category: 'wall', color: '#B2BDA0', roughness: 0.9 },
  { id: 'navy', name: 'Navy', category: 'wall', color: '#2C3E50', roughness: 0.85 },
]

export const CATEGORIES = [...new Set(FURNITURE.map(f => f.category))]
