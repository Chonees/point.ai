/** Furniture and material catalog for 3D editor */

export interface FurnitureItem {
  id: string
  name: string
  category: string
  width: number   // X
  height: number  // Y (up)
  depth: number   // Z
  color: string
  icon: string
}

export interface MaterialPreset {
  id: string
  name: string
  category: 'floor' | 'wall'
  color: string
  roughness: number
  icon: string
}

export const FURNITURE: FurnitureItem[] = [
  // Bedroom
  { id: 'bed-double', name: 'Double Bed', category: 'Bedroom', width: 60, height: 24, depth: 80, color: '#8B7355', icon: '🛏' },
  { id: 'bed-single', name: 'Single Bed', category: 'Bedroom', width: 40, height: 24, depth: 75, color: '#8B7355', icon: '🛏' },
  { id: 'nightstand', name: 'Nightstand', category: 'Bedroom', width: 20, height: 24, depth: 18, color: '#A0522D', icon: '🪑' },
  { id: 'dresser', name: 'Dresser', category: 'Bedroom', width: 48, height: 34, depth: 18, color: '#8B6914', icon: '🗄' },
  { id: 'wardrobe', name: 'Wardrobe', category: 'Bedroom', width: 48, height: 80, depth: 24, color: '#6B4226', icon: '🚪' },

  // Living
  { id: 'sofa-3', name: 'Sofa 3-seat', category: 'Living', width: 84, height: 32, depth: 36, color: '#4A6741', icon: '🛋' },
  { id: 'sofa-2', name: 'Sofa 2-seat', category: 'Living', width: 60, height: 32, depth: 36, color: '#4A6741', icon: '🛋' },
  { id: 'armchair', name: 'Armchair', category: 'Living', width: 32, height: 32, depth: 34, color: '#5C4033', icon: '🪑' },
  { id: 'coffee-table', name: 'Coffee Table', category: 'Living', width: 48, height: 16, depth: 24, color: '#654321', icon: '🪵' },
  { id: 'tv-stand', name: 'TV Stand', category: 'Living', width: 60, height: 20, depth: 16, color: '#333333', icon: '📺' },

  // Kitchen
  { id: 'counter', name: 'Counter', category: 'Kitchen', width: 60, height: 36, depth: 24, color: '#808080', icon: '🍳' },
  { id: 'island', name: 'Island', category: 'Kitchen', width: 48, height: 36, depth: 30, color: '#696969', icon: '🏝' },
  { id: 'fridge', name: 'Refrigerator', category: 'Kitchen', width: 30, height: 70, depth: 30, color: '#C0C0C0', icon: '🧊' },
  { id: 'stove', name: 'Stove', category: 'Kitchen', width: 30, height: 36, depth: 26, color: '#2F2F2F', icon: '🔥' },
  { id: 'sink-k', name: 'Sink', category: 'Kitchen', width: 24, height: 36, depth: 22, color: '#A9A9A9', icon: '🚰' },

  // Bathroom
  { id: 'toilet', name: 'Toilet', category: 'Bathroom', width: 15, height: 16, depth: 28, color: '#F5F5F5', icon: '🚽' },
  { id: 'bathtub', name: 'Bathtub', category: 'Bathroom', width: 30, height: 20, depth: 60, color: '#F0F0F0', icon: '🛁' },
  { id: 'shower', name: 'Shower', category: 'Bathroom', width: 36, height: 80, depth: 36, color: '#E8E8E8', icon: '🚿' },
  { id: 'vanity', name: 'Vanity', category: 'Bathroom', width: 36, height: 34, depth: 20, color: '#D2B48C', icon: '🪞' },

  // Dining
  { id: 'dining-table', name: 'Dining Table', category: 'Dining', width: 60, height: 30, depth: 36, color: '#8B5A2B', icon: '🪑' },
  { id: 'chair', name: 'Chair', category: 'Dining', width: 18, height: 34, depth: 18, color: '#A0522D', icon: '🪑' },

  // Office
  { id: 'desk', name: 'Desk', category: 'Office', width: 48, height: 30, depth: 24, color: '#6B4226', icon: '🖥' },
  { id: 'office-chair', name: 'Office Chair', category: 'Office', width: 22, height: 40, depth: 22, color: '#1a1a1a', icon: '💺' },
  { id: 'bookshelf', name: 'Bookshelf', category: 'Office', width: 36, height: 72, depth: 12, color: '#8B6914', icon: '📚' },
]

export const MATERIALS: MaterialPreset[] = [
  // Floors
  { id: 'hardwood', name: 'Hardwood', category: 'floor', color: '#8B6914', roughness: 0.6, icon: '🪵' },
  { id: 'oak', name: 'Oak', category: 'floor', color: '#C4A265', roughness: 0.55, icon: '🪵' },
  { id: 'walnut', name: 'Walnut', category: 'floor', color: '#5C3317', roughness: 0.6, icon: '🪵' },
  { id: 'tile-white', name: 'White Tile', category: 'floor', color: '#F0EDE8', roughness: 0.3, icon: '⬜' },
  { id: 'tile-gray', name: 'Gray Tile', category: 'floor', color: '#9E9E9E', roughness: 0.35, icon: '🔲' },
  { id: 'marble', name: 'Marble', category: 'floor', color: '#E8E0D8', roughness: 0.15, icon: '🤍' },
  { id: 'carpet-beige', name: 'Beige Carpet', category: 'floor', color: '#C8B896', roughness: 0.95, icon: '🟫' },
  { id: 'carpet-gray', name: 'Gray Carpet', category: 'floor', color: '#808080', roughness: 0.95, icon: '🩶' },
  { id: 'concrete', name: 'Concrete', category: 'floor', color: '#A0A0A0', roughness: 0.8, icon: '🧱' },
  { id: 'lvp', name: 'LVP', category: 'floor', color: '#B8956A', roughness: 0.4, icon: '🪵' },

  // Walls
  { id: 'white-paint', name: 'White Paint', category: 'wall', color: '#F5F5F0', roughness: 0.9, icon: '⬜' },
  { id: 'cream-paint', name: 'Cream', category: 'wall', color: '#F5F0E0', roughness: 0.9, icon: '🟡' },
  { id: 'gray-paint', name: 'Light Gray', category: 'wall', color: '#D0D0D0', roughness: 0.9, icon: '🩶' },
  { id: 'warm-gray', name: 'Warm Gray', category: 'wall', color: '#C8BEB0', roughness: 0.9, icon: '🟤' },
  { id: 'sage', name: 'Sage', category: 'wall', color: '#B2BDA0', roughness: 0.9, icon: '🟢' },
  { id: 'navy', name: 'Navy', category: 'wall', color: '#2C3E50', roughness: 0.85, icon: '🔵' },
  { id: 'brick', name: 'Brick', category: 'wall', color: '#8B4513', roughness: 0.95, icon: '🧱' },
  { id: 'wood-panel', name: 'Wood Panel', category: 'wall', color: '#A0784A', roughness: 0.7, icon: '🪵' },
]

export const CATEGORIES = [...new Set(FURNITURE.map(f => f.category))]
