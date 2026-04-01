/** Furniture and material catalog — uses Kenney Furniture Kit (CC0) GLB models */

export interface FurnitureItem {
  id: string
  name: string
  category: string
  glb: string      // filename in /models/
  scale: number    // uniform scale factor (Kenney models are ~1 unit = 1m)
  icon: string
}

export interface MaterialPreset {
  id: string
  name: string
  category: 'floor' | 'wall'
  color: string
  roughness: number
}

export const FURNITURE: FurnitureItem[] = [
  // Bedroom
  { id: 'bedDouble', name: 'Double Bed', category: 'Bedroom', glb: 'bedDouble.glb', scale: 40, icon: '🛏' },
  { id: 'bedSingle', name: 'Single Bed', category: 'Bedroom', glb: 'bedSingle.glb', scale: 40, icon: '🛏' },
  { id: 'bedBunk', name: 'Bunk Bed', category: 'Bedroom', glb: 'bedBunk.glb', scale: 40, icon: '🛏' },
  { id: 'cabinetBed', name: 'Nightstand', category: 'Bedroom', glb: 'cabinetBed.glb', scale: 40, icon: '🪑' },
  { id: 'cabinetBedDrawer', name: 'Dresser', category: 'Bedroom', glb: 'cabinetBedDrawer.glb', scale: 40, icon: '🗄' },
  { id: 'bookcaseClosedDoors', name: 'Wardrobe', category: 'Bedroom', glb: 'bookcaseClosedDoors.glb', scale: 40, icon: '🚪' },
  { id: 'pillow', name: 'Pillow', category: 'Bedroom', glb: 'pillow.glb', scale: 40, icon: '🛏' },

  // Living
  { id: 'loungeSofa', name: 'Sofa', category: 'Living', glb: 'loungeSofa.glb', scale: 40, icon: '🛋' },
  { id: 'loungeSofaCorner', name: 'Corner Sofa', category: 'Living', glb: 'loungeSofaCorner.glb', scale: 40, icon: '🛋' },
  { id: 'loungeDesignSofa', name: 'Design Sofa', category: 'Living', glb: 'loungeDesignSofa.glb', scale: 40, icon: '🛋' },
  { id: 'loungeChair', name: 'Lounge Chair', category: 'Living', glb: 'loungeChair.glb', scale: 40, icon: '🪑' },
  { id: 'loungeDesignChair', name: 'Design Chair', category: 'Living', glb: 'loungeDesignChair.glb', scale: 40, icon: '🪑' },
  { id: 'tableCoffee', name: 'Coffee Table', category: 'Living', glb: 'tableCoffee.glb', scale: 40, icon: '🪵' },
  { id: 'tableCoffeeGlass', name: 'Glass Coffee Table', category: 'Living', glb: 'tableCoffeeGlass.glb', scale: 40, icon: '🪵' },
  { id: 'cabinetTelevision', name: 'TV Stand', category: 'Living', glb: 'cabinetTelevision.glb', scale: 40, icon: '📺' },
  { id: 'televisionModern', name: 'TV', category: 'Living', glb: 'televisionModern.glb', scale: 40, icon: '📺' },
  { id: 'rugRectangle', name: 'Rug', category: 'Living', glb: 'rugRectangle.glb', scale: 40, icon: '🟫' },

  // Kitchen
  { id: 'kitchenCabinet', name: 'Cabinet', category: 'Kitchen', glb: 'kitchenCabinet.glb', scale: 40, icon: '🍳' },
  { id: 'kitchenCabinetDrawer', name: 'Cabinet Drawer', category: 'Kitchen', glb: 'kitchenCabinetDrawer.glb', scale: 40, icon: '🍳' },
  { id: 'kitchenCabinetUpper', name: 'Upper Cabinet', category: 'Kitchen', glb: 'kitchenCabinetUpper.glb', scale: 40, icon: '🍳' },
  { id: 'kitchenBar', name: 'Kitchen Bar', category: 'Kitchen', glb: 'kitchenBar.glb', scale: 40, icon: '🏝' },
  { id: 'kitchenFridge', name: 'Refrigerator', category: 'Kitchen', glb: 'kitchenFridge.glb', scale: 40, icon: '🧊' },
  { id: 'kitchenStove', name: 'Stove', category: 'Kitchen', glb: 'kitchenStove.glb', scale: 40, icon: '🔥' },
  { id: 'kitchenSink', name: 'Sink', category: 'Kitchen', glb: 'kitchenSink.glb', scale: 40, icon: '🚰' },
  { id: 'kitchenMicrowave', name: 'Microwave', category: 'Kitchen', glb: 'kitchenMicrowave.glb', scale: 40, icon: '📦' },
  { id: 'kitchenCoffeeMachine', name: 'Coffee Machine', category: 'Kitchen', glb: 'kitchenCoffeeMachine.glb', scale: 40, icon: '☕' },
  { id: 'toaster', name: 'Toaster', category: 'Kitchen', glb: 'toaster.glb', scale: 40, icon: '🍞' },

  // Bathroom
  { id: 'toilet', name: 'Toilet', category: 'Bathroom', glb: 'toilet.glb', scale: 40, icon: '🚽' },
  { id: 'toiletSquare', name: 'Square Toilet', category: 'Bathroom', glb: 'toiletSquare.glb', scale: 40, icon: '🚽' },
  { id: 'bathtub', name: 'Bathtub', category: 'Bathroom', glb: 'bathtub.glb', scale: 40, icon: '🛁' },
  { id: 'shower', name: 'Shower', category: 'Bathroom', glb: 'shower.glb', scale: 40, icon: '🚿' },
  { id: 'showerRound', name: 'Round Shower', category: 'Bathroom', glb: 'showerRound.glb', scale: 40, icon: '🚿' },
  { id: 'bathroomSink', name: 'Bathroom Sink', category: 'Bathroom', glb: 'bathroomSink.glb', scale: 40, icon: '🪞' },
  { id: 'bathroomMirror', name: 'Mirror', category: 'Bathroom', glb: 'bathroomMirror.glb', scale: 40, icon: '🪞' },
  { id: 'washer', name: 'Washer', category: 'Bathroom', glb: 'washer.glb', scale: 40, icon: '🧺' },
  { id: 'dryer', name: 'Dryer', category: 'Bathroom', glb: 'dryer.glb', scale: 40, icon: '🧺' },

  // Dining
  { id: 'tableRound', name: 'Round Table', category: 'Dining', glb: 'tableRound.glb', scale: 40, icon: '🪑' },
  { id: 'table', name: 'Table', category: 'Dining', glb: 'table.glb', scale: 40, icon: '🪑' },
  { id: 'tableCloth', name: 'Table w/ Cloth', category: 'Dining', glb: 'tableCloth.glb', scale: 40, icon: '🪑' },
  { id: 'chair', name: 'Chair', category: 'Dining', glb: 'chair.glb', scale: 40, icon: '🪑' },
  { id: 'chairCushion', name: 'Cushion Chair', category: 'Dining', glb: 'chairCushion.glb', scale: 40, icon: '🪑' },
  { id: 'stoolBar', name: 'Bar Stool', category: 'Dining', glb: 'stoolBar.glb', scale: 40, icon: '🪑' },

  // Office
  { id: 'desk', name: 'Desk', category: 'Office', glb: 'desk.glb', scale: 40, icon: '🖥' },
  { id: 'deskCorner', name: 'Corner Desk', category: 'Office', glb: 'deskCorner.glb', scale: 40, icon: '🖥' },
  { id: 'chairDesk', name: 'Office Chair', category: 'Office', glb: 'chairDesk.glb', scale: 40, icon: '💺' },
  { id: 'bookcaseOpen', name: 'Bookcase', category: 'Office', glb: 'bookcaseOpen.glb', scale: 40, icon: '📚' },
  { id: 'computerScreen', name: 'Monitor', category: 'Office', glb: 'computerScreen.glb', scale: 40, icon: '🖥' },
  { id: 'laptop', name: 'Laptop', category: 'Office', glb: 'laptop.glb', scale: 40, icon: '💻' },

  // Decor
  { id: 'pottedPlant', name: 'Plant', category: 'Decor', glb: 'pottedPlant.glb', scale: 40, icon: '🪴' },
  { id: 'plantSmall1', name: 'Small Plant', category: 'Decor', glb: 'plantSmall1.glb', scale: 40, icon: '🌿' },
  { id: 'lampRoundFloor', name: 'Floor Lamp', category: 'Decor', glb: 'lampRoundFloor.glb', scale: 40, icon: '💡' },
  { id: 'lampSquareFloor', name: 'Square Lamp', category: 'Decor', glb: 'lampSquareFloor.glb', scale: 40, icon: '💡' },
  { id: 'lampRoundTable', name: 'Table Lamp', category: 'Decor', glb: 'lampRoundTable.glb', scale: 40, icon: '💡' },
  { id: 'coatRackStanding', name: 'Coat Rack', category: 'Decor', glb: 'coatRackStanding.glb', scale: 40, icon: '🧥' },
  { id: 'trashcan', name: 'Trash Can', category: 'Decor', glb: 'trashcan.glb', scale: 40, icon: '🗑' },
  { id: 'speaker', name: 'Speaker', category: 'Decor', glb: 'speaker.glb', scale: 40, icon: '🔊' },
  { id: 'radio', name: 'Radio', category: 'Decor', glb: 'radio.glb', scale: 40, icon: '📻' },
  { id: 'books', name: 'Books', category: 'Decor', glb: 'books.glb', scale: 40, icon: '📚' },
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
  { id: 'carpet-gray', name: 'Gray Carpet', category: 'floor', color: '#808080', roughness: 0.95 },
  { id: 'concrete', name: 'Concrete', category: 'floor', color: '#A0A0A0', roughness: 0.8 },
  { id: 'lvp', name: 'LVP', category: 'floor', color: '#B8956A', roughness: 0.4 },
  // Walls
  { id: 'white-paint', name: 'White Paint', category: 'wall', color: '#F5F5F0', roughness: 0.9 },
  { id: 'cream-paint', name: 'Cream', category: 'wall', color: '#F5F0E0', roughness: 0.9 },
  { id: 'gray-paint', name: 'Light Gray', category: 'wall', color: '#D0D0D0', roughness: 0.9 },
  { id: 'warm-gray', name: 'Warm Gray', category: 'wall', color: '#C8BEB0', roughness: 0.9 },
  { id: 'sage', name: 'Sage', category: 'wall', color: '#B2BDA0', roughness: 0.9 },
  { id: 'navy', name: 'Navy', category: 'wall', color: '#2C3E50', roughness: 0.85 },
  { id: 'brick', name: 'Brick', category: 'wall', color: '#8B4513', roughness: 0.95 },
  { id: 'wood-panel', name: 'Wood Panel', category: 'wall', color: '#A0784A', roughness: 0.7 },
]

export const CATEGORIES = [...new Set(FURNITURE.map(f => f.category))]
