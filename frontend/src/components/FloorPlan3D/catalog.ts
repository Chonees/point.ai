/** Furniture catalog — ALL ArchViz models (121 GLB from Unreal ArchVisRT) */

export interface FurnitureItem {
  id: string
  name: string
  category: string
  glb: string
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

const AV = 'archviz/'
const S = 80

export const FURNITURE: FurnitureItem[] = [
  // Living Room
  { id: 'couch', name: 'Couch', category: 'Living', glb: `${AV}SM_Couch.glb`, scale: S, icon: '🛋' },
  { id: 'livingchair', name: 'Armchair', category: 'Living', glb: `${AV}SM_LivingRoomChair.glb`, scale: S, icon: '🪑' },
  { id: 'coffeetable', name: 'Coffee Table', category: 'Living', glb: `${AV}SM_CoffeeTable.glb`, scale: S, icon: '🪵' },
  { id: 'sidetable', name: 'Side Table', category: 'Living', glb: `${AV}SM_SideTable.glb`, scale: S, icon: '🪵' },
  { id: 'sidetable1', name: 'Side Table 2', category: 'Living', glb: `${AV}SM_SideTable_01.glb`, scale: S, icon: '🪵' },
  { id: 'sidetable2', name: 'Side Table 3', category: 'Living', glb: `${AV}SM_SideTable_02.glb`, scale: S, icon: '🪵' },
  { id: 'sidetableshelf', name: 'Shelf Table', category: 'Living', glb: `${AV}SM_SideTableShelf.glb`, scale: S, icon: '🪵' },
  { id: 'tv', name: 'TV', category: 'Living', glb: `${AV}SM_TV.glb`, scale: S, icon: '📺' },
  { id: 'tvstand', name: 'TV Stand', category: 'Living', glb: `${AV}SM_TVStand.glb`, scale: S, icon: '📺' },
  { id: 'tvshelf-l', name: 'TV Shelf Large', category: 'Living', glb: `${AV}SM_TVStandShelf_Large.glb`, scale: S, icon: '📺' },
  { id: 'tvshelf-s', name: 'TV Shelf Small', category: 'Living', glb: `${AV}SM_TVStandShelf_Small.glb`, scale: S, icon: '📺' },
  { id: 'dvdplayer', name: 'DVD Player', category: 'Living', glb: `${AV}SM_DVDPlayer.glb`, scale: S, icon: '📀' },
  { id: 'tvremote', name: 'TV Remote', category: 'Living', glb: `${AV}SM_TVRemote.glb`, scale: S, icon: '📱' },
  { id: 'rug', name: 'Rug', category: 'Living', glb: `${AV}SM_Rug_01.glb`, scale: S, icon: '🟫' },
  { id: 'radiator', name: 'Radiator', category: 'Living', glb: `${AV}SM_Radiator.glb`, scale: S, icon: '🔥' },

  // Dining
  { id: 'diningtable', name: 'Dining Table', category: 'Dining', glb: `${AV}SM_DiningTable.glb`, scale: S, icon: '🪑' },
  { id: 'diningchair', name: 'Dining Chair', category: 'Dining', glb: `${AV}SM_DiningChair_01.glb`, scale: S, icon: '🪑' },
  { id: 'diningrug', name: 'Dining Rug', category: 'Dining', glb: `${AV}SM_DiningRoomRug.glb`, scale: S, icon: '🟫' },
  { id: 'glass1', name: 'Glass', category: 'Dining', glb: `${AV}SM_Glass_01.glb`, scale: S, icon: '🥃' },
  { id: 'glass3', name: 'Glass 2', category: 'Dining', glb: `${AV}SM_Glass_03.glb`, scale: S, icon: '🥃' },
  { id: 'bowl', name: 'Bowl', category: 'Dining', glb: `${AV}SM_Bowl_01.glb`, scale: S, icon: '🥣' },
  { id: 'tray', name: 'Tray', category: 'Dining', glb: `${AV}SM_Tray.glb`, scale: S, icon: '🍽' },
  { id: 'apple', name: 'Apple', category: 'Dining', glb: `${AV}SM_Apple.glb`, scale: S, icon: '🍎' },

  // Shelves & Storage
  { id: 'shelf', name: 'Shelf', category: 'Storage', glb: `${AV}SM_Shelf.glb`, scale: S, icon: '📚' },
  { id: 'laddershelf', name: 'Ladder Shelf', category: 'Storage', glb: `${AV}SM_LadderShelf.glb`, scale: S, icon: '📚' },
  { id: 'basket', name: 'Basket', category: 'Storage', glb: `${AV}SM_Basket.glb`, scale: S, icon: '🧺' },
  { id: 'box', name: 'Box', category: 'Storage', glb: `${AV}SM_Box_01.glb`, scale: S, icon: '📦' },
  { id: 'boxlid', name: 'Box with Lid', category: 'Storage', glb: `${AV}SM_BoxLid_01.glb`, scale: S, icon: '📦' },
  { id: 'coatrack', name: 'Coat Rack', category: 'Storage', glb: `${AV}SM_CoatRack.glb`, scale: S, icon: '🧥' },
  { id: 'coat', name: 'Coat', category: 'Storage', glb: `${AV}SM_Coat.glb`, scale: S, icon: '🧥' },
  { id: 'ue4bag', name: 'Bag', category: 'Storage', glb: `${AV}SM_UE4Bag.glb`, scale: S, icon: '👜' },

  // Lighting
  { id: 'standinglamp', name: 'Standing Lamp', category: 'Lighting', glb: `${AV}SM_StandingLamp.glb`, scale: S, icon: '💡' },
  { id: 'hanginglight', name: 'Hanging Light', category: 'Lighting', glb: `${AV}SM_HangingLight.glb`, scale: S, icon: '💡' },
  { id: 'candle', name: 'Candle', category: 'Lighting', glb: `${AV}SM_Candle.glb`, scale: S, icon: '🕯' },
  { id: 'candlestick', name: 'Candlestick', category: 'Lighting', glb: `${AV}SM_CandleStick.glb`, scale: S, icon: '🕯' },

  // Curtains & Windows
  { id: 'curtainback', name: 'Curtain Back', category: 'Windows', glb: `${AV}SM_CurtainBack.glb`, scale: S, icon: '🪟' },
  { id: 'curtainfront', name: 'Curtain Front', category: 'Windows', glb: `${AV}SM_CurtainFront.glb`, scale: S, icon: '🪟' },
  { id: 'curtainframe', name: 'Curtain Frame', category: 'Windows', glb: `${AV}SM_CurtainFrame.glb`, scale: S, icon: '🪟' },
  { id: 'curtainframetop', name: 'Curtain Frame Top', category: 'Windows', glb: `${AV}SM_CurtainFrameTop.glb`, scale: S, icon: '🪟' },
  { id: 'blinds1', name: 'Blinds', category: 'Windows', glb: `${AV}SM_Blinds_01.glb`, scale: S, icon: '🪟' },
  { id: 'blinds2', name: 'Blinds 2', category: 'Windows', glb: `${AV}SM_Blinds_02.glb`, scale: S, icon: '🪟' },
  { id: 'blinds3', name: 'Blinds 3', category: 'Windows', glb: `${AV}SM_Blinds_03.glb`, scale: S, icon: '🪟' },
  { id: 'blinds4', name: 'Blinds 4', category: 'Windows', glb: `${AV}SM_Blinds_04.glb`, scale: S, icon: '🪟' },
  { id: 'windowframe', name: 'Window Frame', category: 'Windows', glb: `${AV}SM_Windowframe.glb`, scale: S, icon: '🪟' },
  { id: 'windowsill-dr', name: 'Window Sill DR', category: 'Windows', glb: `${AV}SM_WindowSill_DR.glb`, scale: S, icon: '🪟' },
  { id: 'windowsill-lr', name: 'Window Sill LR', category: 'Windows', glb: `${AV}SM_WindowSill_LR.glb`, scale: S, icon: '🪟' },

  // Doors & Building
  { id: 'door', name: 'Door', category: 'Building', glb: `${AV}SM_Door.glb`, scale: S, icon: '🚪' },
  { id: 'doorframe-in', name: 'Door Frame Inner', category: 'Building', glb: `${AV}SM_DoorFrame_Inner.glb`, scale: S, icon: '🚪' },
  { id: 'doorframe-out', name: 'Door Frame Outer', category: 'Building', glb: `${AV}SM_DoorFrame_Outer.glb`, scale: S, icon: '🚪' },
  { id: 'doorhandle', name: 'Door Handle', category: 'Building', glb: `${AV}SM_DoorHandle.glb`, scale: S, icon: '🚪' },
  { id: 'ceiling', name: 'Ceiling', category: 'Building', glb: `${AV}SM_Ceiling.glb`, scale: S, icon: '⬜' },
  { id: 'floor', name: 'Floor', category: 'Building', glb: `${AV}SM_Floor.glb`, scale: S, icon: '⬜' },
  { id: 'socket', name: 'Socket', category: 'Building', glb: `${AV}SM_Socket.glb`, scale: S, icon: '🔌' },
  { id: 'switch', name: 'Light Switch', category: 'Building', glb: `${AV}SM_Switch.glb`, scale: S, icon: '🔌' },
  { id: 'wall-back', name: 'Wall Back', category: 'Building', glb: `${AV}SM_Wall_Back.glb`, scale: S, icon: '🧱' },
  { id: 'wall-front', name: 'Wall Front', category: 'Building', glb: `${AV}SM_Wall_Front.glb`, scale: S, icon: '🧱' },
  { id: 'wall-left', name: 'Wall Left', category: 'Building', glb: `${AV}SM_Wall_Left.glb`, scale: S, icon: '🧱' },
  { id: 'wall-right', name: 'Wall Right', category: 'Building', glb: `${AV}SM_Wall_Right.glb`, scale: S, icon: '🧱' },

  // Bedroom / Comfort
  { id: 'pillow1', name: 'Pillow', category: 'Bedroom', glb: `${AV}SM_Pillow_01.glb`, scale: S, icon: '🛏' },
  { id: 'pillow2', name: 'Pillow 2', category: 'Bedroom', glb: `${AV}SM_Pillow_02.glb`, scale: S, icon: '🛏' },
  { id: 'pillow3', name: 'Pillow 3', category: 'Bedroom', glb: `${AV}SM_Pillow_03.glb`, scale: S, icon: '🛏' },
  { id: 'pillow4', name: 'Pillow 4', category: 'Bedroom', glb: `${AV}SM_Pillow_04.glb`, scale: S, icon: '🛏' },
  { id: 'blanket1', name: 'Throw Blanket', category: 'Bedroom', glb: `${AV}SM_ThrowBlanket_01.glb`, scale: S, icon: '🧣' },
  { id: 'blanket2', name: 'Throw Blanket 2', category: 'Bedroom', glb: `${AV}SM_ThrowBlanket_02.glb`, scale: S, icon: '🧣' },
  { id: 'cradle', name: 'Cradle Base', category: 'Bedroom', glb: `${AV}SM_CradleBase.glb`, scale: S, icon: '🍼' },

  // Decor & Art
  { id: 'vase1', name: 'Vase', category: 'Decor', glb: `${AV}SM_Vase_01.glb`, scale: S, icon: '🏺' },
  { id: 'vase2', name: 'Vase 2', category: 'Decor', glb: `${AV}SM_Vase_02.glb`, scale: S, icon: '🏺' },
  { id: 'vase3', name: 'Vase 3', category: 'Decor', glb: `${AV}SM_Vase_03.glb`, scale: S, icon: '🏺' },
  { id: 'vase4', name: 'Vase 4', category: 'Decor', glb: `${AV}SM_Vase_04.glb`, scale: S, icon: '🏺' },
  { id: 'vase5', name: 'Vase 5', category: 'Decor', glb: `${AV}SM_Vase_05.glb`, scale: S, icon: '🏺' },
  { id: 'vase6', name: 'Vase 6', category: 'Decor', glb: `${AV}SM_Vase_06.glb`, scale: S, icon: '🏺' },
  { id: 'frame1', name: 'Frame', category: 'Decor', glb: `${AV}SM_Frame_01.glb`, scale: S, icon: '🖼' },
  { id: 'frame3', name: 'Frame 2', category: 'Decor', glb: `${AV}SM_Frame_03.glb`, scale: S, icon: '🖼' },
  { id: 'picture1', name: 'Picture', category: 'Decor', glb: `${AV}SM_Picture_01.glb`, scale: S, icon: '🖼' },
  { id: 'picture2', name: 'Picture 2', category: 'Decor', glb: `${AV}SM_Picture_02.glb`, scale: S, icon: '🖼' },
  { id: 'picture3', name: 'Picture 3', category: 'Decor', glb: `${AV}SM_Picture_03.glb`, scale: S, icon: '🖼' },
  { id: 'picture4', name: 'Picture 4', category: 'Decor', glb: `${AV}SM_Picture_04.glb`, scale: S, icon: '🖼' },
  { id: 'picture5', name: 'Picture 5', category: 'Decor', glb: `${AV}SM_Picture_05.glb`, scale: S, icon: '🖼' },
  { id: 'book1', name: 'Books', category: 'Decor', glb: `${AV}SM_Book_01.glb`, scale: S, icon: '📚' },
  { id: 'book2', name: 'Books 2', category: 'Decor', glb: `${AV}SM_Book_02.glb`, scale: S, icon: '📚' },
  { id: 'book3', name: 'Books 3', category: 'Decor', glb: `${AV}SM_Book_03.glb`, scale: S, icon: '📚' },
  { id: 'book4', name: 'Books 4', category: 'Decor', glb: `${AV}SM_Book_04.glb`, scale: S, icon: '📚' },
  { id: 'book5', name: 'Books 5', category: 'Decor', glb: `${AV}SM_Book_05.glb`, scale: S, icon: '📚' },
  { id: 'book6', name: 'Books 6', category: 'Decor', glb: `${AV}SM_Book_06.glb`, scale: S, icon: '📚' },
  { id: 'newspaper', name: 'Newspaper', category: 'Decor', glb: `${AV}SM_Newspaper.glb`, scale: S, icon: '📰' },
  { id: 'torus', name: 'Torus Sculpture', category: 'Decor', glb: `${AV}SM_Torus.glb`, scale: S, icon: '⭕' },
  { id: 'top', name: 'Decorative Top', category: 'Decor', glb: `${AV}SM_Top.glb`, scale: S, icon: '🎨' },

  // Fan
  { id: 'fanbar', name: 'Fan Bar', category: 'Appliances', glb: `${AV}SM_FanBar.glb`, scale: S, icon: '🌀' },
  { id: 'fanbase', name: 'Fan Base', category: 'Appliances', glb: `${AV}SM_FanBase.glb`, scale: S, icon: '🌀' },
  { id: 'fanbody', name: 'Fan Body', category: 'Appliances', glb: `${AV}SM_FanBody.glb`, scale: S, icon: '🌀' },

  // Plants
  { id: 'aglaonema1', name: 'Aglaonema', category: 'Plants', glb: `${AV}SM_Aglaonema_01.glb`, scale: S, icon: '🌿' },
  { id: 'aglaonema2', name: 'Aglaonema 2', category: 'Plants', glb: `${AV}SM_Aglaonema_02.glb`, scale: S, icon: '🌿' },
  { id: 'aglaonema3', name: 'Aglaonema 3', category: 'Plants', glb: `${AV}SM_Aglaonema_03.glb`, scale: S, icon: '🌿' },
  { id: 'amaryllis1', name: 'Amaryllis', category: 'Plants', glb: `${AV}SM_Amaryllis_01.glb`, scale: S, icon: '🌺' },
  { id: 'amaryllis2', name: 'Amaryllis 2', category: 'Plants', glb: `${AV}SM_Amaryllis_02.glb`, scale: S, icon: '🌺' },
  { id: 'chloro', name: 'Spider Plant', category: 'Plants', glb: `${AV}SM_Chlorophytum_01.glb`, scale: S, icon: '🌿' },
  { id: 'dracaena1', name: 'Dracaena', category: 'Plants', glb: `${AV}SM_Dracaena_01.glb`, scale: S, icon: '🌴' },
  { id: 'dracaena2', name: 'Dracaena 2', category: 'Plants', glb: `${AV}SM_Dracaena_02.glb`, scale: S, icon: '🌴' },
  { id: 'dracaena3', name: 'Dracaena 3', category: 'Plants', glb: `${AV}SM_Dracaena_03.glb`, scale: S, icon: '🌴' },
  { id: 'dracaena4', name: 'Dracaena 4', category: 'Plants', glb: `${AV}SM_Dracaena_04.glb`, scale: S, icon: '🌴' },
  { id: 'dracaena5', name: 'Dracaena 5', category: 'Plants', glb: `${AV}SM_Dracaena_05.glb`, scale: S, icon: '🌴' },
  { id: 'snake1', name: 'Snake Plant', category: 'Plants', glb: `${AV}SM_SnakePlant_01.glb`, scale: S, icon: '🪴' },
  { id: 'snake2', name: 'Snake Plant 2', category: 'Plants', glb: `${AV}SM_SnakePlant_02.glb`, scale: S, icon: '🪴' },
  { id: 'snake3', name: 'Snake Plant 3', category: 'Plants', glb: `${AV}SM_SnakePlant_03.glb`, scale: S, icon: '🪴' },
  { id: 'hedra1', name: 'Ivy', category: 'Plants', glb: `${AV}SM_Hedra_01.glb`, scale: S, icon: '🌱' },
  { id: 'hedra2', name: 'Ivy 2', category: 'Plants', glb: `${AV}SM_Hedra_02.glb`, scale: S, icon: '🌱' },
  { id: 'hedra3', name: 'Ivy 3', category: 'Plants', glb: `${AV}SM_Hedra_03.glb`, scale: S, icon: '🌱' },
  { id: 'spring', name: 'Spring Plant', category: 'Plants', glb: `${AV}SM_Spring_01.glb`, scale: S, icon: '🌸' },
  { id: 'soil', name: 'Soil', category: 'Plants', glb: `${AV}SM_Soil.glb`, scale: S, icon: '🪴' },
  { id: 'pot3', name: 'Pot', category: 'Plants', glb: `${AV}SM_Pot_03.glb`, scale: S, icon: '🪴' },
  { id: 'pot4', name: 'Pot 2', category: 'Plants', glb: `${AV}SM_Pot_04.glb`, scale: S, icon: '🪴' },
  { id: 'pot5', name: 'Pot 3', category: 'Plants', glb: `${AV}SM_Pot_05.glb`, scale: S, icon: '🪴' },
  { id: 'potstand', name: 'Pot Stand', category: 'Plants', glb: `${AV}SM_PotStand_01.glb`, scale: S, icon: '🪴' },
]

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

export const CATEGORIES = [...new Set(FURNITURE.map(f => f.category))]
