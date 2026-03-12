# Rooms that should NEVER have windows (interior-only rooms)
NO_WINDOW_ROOMS = {
    "BATH", "BATHROOM", "BATH 1", "BATH 2", "BATH 3",
    "CLOSET", "WIC", "WALK-IN CLOSET", "PANTRY",
    "LAUNDRY", "UTILITY", "HALL", "HALLWAY", "CORRIDOR",
}


def _rooms_share_wall(r1: dict, r2: dict, wall: str) -> bool:
    """Check if room r1's wall is shared (interior) with room r2."""
    x1, y1, w1, h1 = r1["x"], r1["y"], r1["w"], r1["h"]
    x2, y2, w2, h2 = r2["x"], r2["y"], r2["w"], r2["h"]

    if wall == "left":
        return abs(x1 - (x2 + w2)) < 5 and y1 < y2 + h2 and y1 + h1 > y2
    elif wall == "right":
        return abs((x1 + w1) - x2) < 5 and y1 < y2 + h2 and y1 + h1 > y2
    elif wall == "bottom":
        return abs(y1 - (y2 + h2)) < 5 and x1 < x2 + w2 and x1 + w1 > x2
    elif wall == "top":
        return abs((y1 + h1) - y2) < 5 and x1 < x2 + w2 and x1 + w1 > x2
    return False


def _is_interior_wall(room: dict, wall: str, all_rooms: list) -> bool:
    """Check if a wall is interior (shared with another room)."""
    for other in all_rooms:
        if other is room:
            continue
        if _rooms_share_wall(room, other, wall):
            return True
    return False


def validate_plan(plan: dict) -> dict:
    """Fix common door/window mistakes in Claude's output."""
    rooms = plan.get("rooms", [])

    for room in rooms:
        name = room.get("name", "").upper()
        doors = room.get("doors", [])
        windows = room.get("windows", [])

        # Rule 1: Remove windows from rooms that should never have them
        if any(name.startswith(prefix) for prefix in NO_WINDOW_ROOMS):
            if windows:
                room["windows"] = []
            continue

        # Rule 2: Move windows on interior walls to doors
        new_windows = []
        for win in windows:
            wall = win.get("wall", "")
            if _is_interior_wall(room, wall, rooms):
                doors.append({
                    "wall": wall,
                    "offset": win["offset"],
                    "width": max(win.get("width", 36), 32),
                    "type": "normal",
                })
            else:
                new_windows.append(win)
        room["windows"] = new_windows
        room["doors"] = doors

        # Rule 3: Every room must have at least one door
        if not doors:
            for wall in ["bottom", "top", "left", "right"]:
                if _is_interior_wall(room, wall, rooms):
                    room["doors"] = [{"wall": wall, "offset": 20, "width": 32, "type": "normal"}]
                    break

    return plan
