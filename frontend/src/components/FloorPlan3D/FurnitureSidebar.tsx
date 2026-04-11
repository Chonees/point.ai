import { useMemo, useState } from 'react'
import {
  CATEGORIES,
  COLOR_PALETTE,
  FURNITURE,
  MATERIALS,
  getSubcategories,
  type FurnitureItem,
  type MaterialPreset,
} from './catalog'
import { ThumbnailCard } from './ThumbnailCard'

/* ------------------------------------------------------------------ */
/*  Icons per subcategory                                              */
/* ------------------------------------------------------------------ */

const SUB_ICONS: Record<string, string> = {
  armchair: '🪑', lounge_chair: '🪑', office_chair: '💺', kitchen_chair: '🪑',
  sofa: '🛋', ottoman: '🪑',
  coffee_table: '🪵', kitchen_table: '🍽', office_table: '🖥',
  bed: '🛏', closet: '🗄', carpet: '🟫',
  shelf: '📚', clothes: '👔',
  kitchen_item: '🍳', bathroom_item: '🚿',
  lamp: '💡', flower: '🌿', picture: '🖼', Curtains: '🪟',
  electronics: '📱', entertainment: '🎮', tv_wall: '📺', musical_instrument: '🎸',
  door: '🚪', window: '🪟', wall: '🧱', Walls: '🧱', Partitions: '🧱', Stairs: '🪜', floor: '⬜',
  for_kids: '🧸', toy: '🎯', training_item: '🏋',
  prop: '📦', shop: '🏪', warehouse: '🏭',
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PlacedFurniture {
  item: FurnitureItem
  x: number
  y: number
  z: number
  rotation: number
  scaleW: number
  scaleD: number
  tintColor?: string
}

interface FurnitureSidebarProps {
  tab: 'furniture' | 'materials'
  setTab: (tab: 'furniture' | 'materials') => void
  selectedItem: FurnitureItem | null
  setSelectedItem: (item: FurnitureItem | null) => void
  placed: PlacedFurniture[]
  selectedPlaced: number
  setSelectedPlaced: (index: number) => void
  rotatePlaced: (index: number) => void
  removePlaced: (index: number) => void
  setPlacedTint: (index: number, color: string | undefined) => void
  floorMat: MaterialPreset
  setFloorMat: (mat: MaterialPreset) => void
  wallMat: MaterialPreset
  setWallMat: (mat: MaterialPreset) => void
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function FurnitureSidebar({
  tab, setTab,
  selectedItem, setSelectedItem,
  placed, selectedPlaced, setSelectedPlaced,
  rotatePlaced, removePlaced, setPlacedTint,
  floorMat, setFloorMat,
  wallMat, setWallMat,
}: FurnitureSidebarProps) {
  const [category, setCategory] = useState(CATEGORIES[0])
  const [subcategory, setSubcategory] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [visibleCount, setVisibleCount] = useState(24)

  const subcategories = useMemo(() => getSubcategories(category), [category])

  const filteredItems = useMemo(() => {
    let items = FURNITURE
    if (search.trim()) {
      const q = search.toLowerCase()
      items = items.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.subcategory.toLowerCase().includes(q) ||
          f.category.toLowerCase().includes(q),
      )
    } else {
      items = items.filter((f) => f.category === category)
      if (subcategory) items = items.filter((f) => f.subcategory === subcategory)
    }
    return items
  }, [category, subcategory, search])

  const activeTint = selectedPlaced >= 0 ? placed[selectedPlaced]?.tintColor : undefined

  return (
    <div className="flex w-80 flex-shrink-0 flex-col overflow-hidden border-r border-zinc-800/60 bg-zinc-900">
      {/* Tab bar */}
      <div className="flex border-b border-zinc-800/40">
        {(['furniture', 'materials'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 cursor-pointer py-2.5 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              tab === t
                ? 'bg-zinc-800/50 text-zinc-200'
                : 'text-zinc-500 hover:text-zinc-400'
            }`}
          >
            {t === 'furniture' ? 'Furniture' : 'Materials'}
          </button>
        ))}
      </div>

      {tab === 'furniture' ? (
        <>
          {/* Search */}
          <div className="border-b border-zinc-800/30 p-2">
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setVisibleCount(24) }}
              placeholder="Search furniture..."
              className="w-full rounded-md border border-zinc-700/40 bg-zinc-800/60 px-3 py-1.5 text-[11px] text-zinc-300 placeholder-zinc-600 outline-none focus:border-blue-600/50"
            />
          </div>

          {/* Categories (hidden when searching) */}
          {!search.trim() && (
            <>
              <div className="flex flex-wrap gap-1 border-b border-zinc-800/30 p-2">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => {
                      setCategory(cat)
                      setSubcategory(null)
                      setVisibleCount(24)
                    }}
                    className={`cursor-pointer rounded-md px-2 py-1 text-[10px] font-medium transition-colors ${
                      cat === category
                        ? 'bg-blue-600/30 text-blue-300 ring-1 ring-blue-600/40'
                        : 'bg-zinc-800/50 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-400'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              {/* Subcategories */}
              {subcategories.length > 1 && (
                <div className="flex flex-wrap gap-1 border-b border-zinc-800/20 px-2 py-1.5">
                  <button
                    onClick={() => setSubcategory(null)}
                    className={`cursor-pointer rounded px-1.5 py-0.5 text-[9px] transition-colors ${
                      !subcategory
                        ? 'bg-zinc-700/60 text-zinc-300'
                        : 'text-zinc-600 hover:text-zinc-400'
                    }`}
                  >
                    All
                  </button>
                  {subcategories.map((sub) => (
                    <button
                      key={sub}
                      onClick={() => { setSubcategory(sub === subcategory ? null : sub); setVisibleCount(24) }}
                      className={`cursor-pointer rounded px-1.5 py-0.5 text-[9px] transition-colors ${
                        sub === subcategory
                          ? 'bg-zinc-700/60 text-zinc-300'
                          : 'text-zinc-600 hover:text-zinc-400'
                      }`}
                    >
                      {SUB_ICONS[sub] || '•'} {sub.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Items grid */}
          <div className="flex-1 overflow-y-auto p-2">
            <p className="mb-1.5 flex items-center justify-between px-0.5 text-[9px] text-zinc-600">
              <span>{filteredItems.length} items</span>
              {visibleCount < filteredItems.length && (
                <span className="text-zinc-700">
                  showing {visibleCount}
                </span>
              )}
            </p>
            <div className="grid grid-cols-3 gap-1.5">
              {filteredItems.slice(0, visibleCount).map((item) => (
                <ThumbnailCard
                  key={item.id}
                  item={item}
                  selected={selectedItem?.id === item.id}
                  onClick={() =>
                    setSelectedItem(selectedItem?.id === item.id ? null : item)
                  }
                />
              ))}
            </div>
            {visibleCount < filteredItems.length && (
              <button
                onClick={() => setVisibleCount((c) => c + 30)}
                className="mt-2 w-full cursor-pointer rounded-md bg-zinc-800/50 py-2 text-[10px] text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
              >
                Load more ({filteredItems.length - visibleCount} remaining)
              </button>
            )}
          </div>

          {/* Placement hint */}
          {selectedItem && (
            <div className="border-t border-zinc-800/40 bg-blue-900/20 p-2.5 text-center text-[10px] text-blue-300">
              Click on the floor to place <strong>{selectedItem.name}</strong>
            </div>
          )}

          {/* Color picker (when a placed item is selected) */}
          {selectedPlaced >= 0 && (
            <div className="border-t border-zinc-800/40 p-2">
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-[10px] font-medium text-zinc-400">Color Tint</p>
                <div className="flex gap-2">
                  {activeTint && (
                    <button
                      onClick={() => setPlacedTint(selectedPlaced, undefined)}
                      className="cursor-pointer text-[9px] text-zinc-600 hover:text-zinc-400"
                    >
                      Reset
                    </button>
                  )}
                  <button
                    onClick={() => setSelectedPlaced(-1)}
                    className="cursor-pointer text-[13px] leading-none text-zinc-600 hover:text-zinc-300"
                    title="Close"
                  >
                    ✕
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-9 gap-0.5">
                {COLOR_PALETTE.map((color) => (
                  <button
                    key={`${color.row}-${color.col}`}
                    onClick={() => setPlacedTint(selectedPlaced, color.hex)}
                    className="cursor-pointer rounded-sm transition-transform hover:scale-125"
                    style={{
                      backgroundColor: color.hex,
                      width: '100%',
                      aspectRatio: '1',
                      outline: activeTint === color.hex ? '2px solid #60a5fa' : 'none',
                      outlineOffset: '1px',
                    }}
                    title={color.hex}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        /* Materials tab */
        <div className="flex-1 space-y-3 overflow-y-auto p-2.5">
          <div>
            <p className="mb-1.5 px-0.5 text-[10px] font-medium text-zinc-500">Floor</p>
            <div className="grid grid-cols-2 gap-1">
              {MATERIALS.filter((m) => m.category === 'floor').map((mat) => (
                <button
                  key={mat.id}
                  onClick={() => setFloorMat(mat)}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-colors ${
                    mat.id === floorMat.id
                      ? 'border-blue-600/40 bg-blue-900/25'
                      : 'border-zinc-800/30 hover:bg-zinc-800/40'
                  }`}
                >
                  <span className="h-5 w-5 flex-shrink-0 rounded" style={{ background: mat.color }} />
                  <span className="text-[10px] text-zinc-400">{mat.name}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-1.5 px-0.5 text-[10px] font-medium text-zinc-500">Walls</p>
            <div className="grid grid-cols-2 gap-1">
              {MATERIALS.filter((m) => m.category === 'wall').map((mat) => (
                <button
                  key={mat.id}
                  onClick={() => setWallMat(mat)}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-colors ${
                    mat.id === wallMat.id
                      ? 'border-blue-600/40 bg-blue-900/25'
                      : 'border-zinc-800/30 hover:bg-zinc-800/40'
                  }`}
                >
                  <span className="h-5 w-5 flex-shrink-0 rounded" style={{ background: mat.color }} />
                  <span className="text-[10px] text-zinc-400">{mat.name}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Placed items list */}
      {placed.length > 0 && (
        <div className="max-h-40 overflow-y-auto border-t border-zinc-800/40 p-2">
          <p className="mb-1 px-0.5 text-[9px] font-medium text-zinc-600">
            Placed ({placed.length})
          </p>
          <div className="space-y-0.5">
            {placed.map((p, i) => (
              <div
                key={`${p.item.id}-${i}`}
                className={`flex items-center justify-between rounded-md px-2 py-1.5 text-[10px] transition-colors ${
                  selectedPlaced === i
                    ? 'bg-zinc-800/70 text-zinc-300'
                    : 'text-zinc-500 hover:bg-zinc-800/30'
                }`}
              >
                <span
                  className="flex cursor-pointer items-center gap-1.5 hover:text-zinc-300"
                  onClick={() => setSelectedPlaced(selectedPlaced === i ? -1 : i)}
                >
                  {p.tintColor && (
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: p.tintColor }}
                    />
                  )}
                  {SUB_ICONS[p.item.subcategory] || '📦'} {p.item.name}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => rotatePlaced(i)}
                    className="cursor-pointer text-zinc-600 hover:text-zinc-300"
                  >
                    ↻
                  </button>
                  <button
                    onClick={() => removePlaced(i)}
                    className="cursor-pointer text-zinc-600 hover:text-red-400"
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
