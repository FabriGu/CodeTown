"""Construction site yards along the front of the town (from mock_roles.construction)."""

SITE_COLUMNS = 6


def _top_folder(path):
    return path.split("/")[0] + "/" if "/" in path else path


def layout_sites(tmap, site_paths):
    lots = {m: (b.x, b.y, b.size) for m, b in tmap.buildings.items()}
    if not site_paths:
        return {}
    folders = {}
    for p in site_paths:
        folders.setdefault(_top_folder(p), []).append(p)
    top = max(y + s for _, y, s in lots.values()) + 1
    width = tmap.width - 2
    sites, x, y, deepest = {}, 0, top, 0
    for members in folders.values():
        cols = min(SITE_COLUMNS, len(members))
        if x and x + cols > width:
            x, y = 0, y + deepest + 1
        for i, p in enumerate(sorted(members)):
            sites[p] = (x + i % cols, y + i // cols, 1)
        deepest = max(deepest, -(-len(members) // cols))
        x += cols + 1
    return sites
