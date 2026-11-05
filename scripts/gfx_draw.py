"""Find the Japanese drawn in a graphics block, and draw English labels in its place (stage 03b).

usage: gfx_draw.py find ROM TBL BIN BPP
       gfx_draw.py draw ROM TBL MAP OUTDIR [ID ...]

A block is seen as one picture, 16 tiles (128 px) wide, or "tiles_wide" in its gfx-map.json entry when
its labels are laid out in shorter rows. A label line that runs past the right edge goes on 16 px lower
at the left edge (the next pair of tile rows), so the picture is searched as if each line were longer.

find: lists every run of characters from the game's 12 x 12 font (bank $95) drawn in one colour:
      y, x, colour and the text (decoded with TBL).
draw: for each block in MAP (gfx-map.json) with a "labels" list (or only the IDs given), copies
      ORIGINAL/Gxx.bin, and for each label {"jp", "en", "font"[, "align", "near", "dx", "dy"]}:
      finds "jp" as a run of font characters (the one nearest "near" [x, y] if it occurs more than
      once), sets its character pixels to the label's background colour (the commonest other colour
      in the 12-row cell), and draws "en" in the character colour, centred in the cells ("align":
      "left" or "right" to start or end at the box's edge; an empty "en" only clears the box). Fonts: "narrow" (narrow-font.txt, 6 px a letter), "latin"
      (latin-font.txt, 12-px letters, spaced by their own width; a space is 4 px), "small" and "tiny" (gfx-fonts.txt).
      A label whose characters the artist changed (so they do not match the font) is given by hand:
      "at": [x, y], "w" (and "h", default 12); its colours are the two commonest in that box, or
      "fg" / "bg". "clear": the colours to wipe in the box (default: the text colour); "outline": a
      colour drawn around the new letters, for two-tone text ("border": a ring inside the outline).
      "shadow": a colour one pixel right and down of the letters.
      "gap": px between letters (default: the set's own). "shade_rows": colours by row, top to bottom. "shade": colours across each letter, left
      to right (for letters with a shine, e.g. [7, 7, 8, 8, 9, 9, 15, 9, 9]). "fill": "near" for text
      drawn over a picture: the cleared pixels take the colours around them (not one background
      colour), and the outline is drawn over any colour. "checker": [a, b] refills the cleared pixels with a
      two-colour dither (a where x + y is even), for text on a see-through box. "grid": rows of tile numbers that make up
      the label's box when its halves are stored apart ("at" is then inside that box). The extra letter sets come from OUTDIR/gfx-fonts.txt ("== name" starts a set).
      Writes OUTDIR/edited/Gxx.bin and .png, and OUTDIR/compare/Gxx.png (original above, edited below).
      A screen layout block with "map_edits" [{"x", "y", "old", "tile"}] gets those tile map entries changed
      ("old" and "tile" may be lists: a run of entries from x to the right).
      The original files come from OUTDIR/original/Gxx.bin. Stops if an English label is wider than
      its Japanese cells.
"""
import json
import os
import re
import sys

from gfx_unpack import tile_pixels, write_png
from tbl import load_tbl

FONT_BASE, GLYPHS = 0x0A8000, 1320
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "..", "stages")


def game_font(rom):
    """{12 row bitmaps: glyph code} for the 12 x 12 font."""
    out = {}
    for g in range(GLYPHS):
        b = rom[FONT_BASE + 24 * g:FONT_BASE + 24 * g + 24]
        rows = tuple(int.from_bytes(b[2 * r:2 * r + 2], "big") >> 4 for r in range(12))
        if any(rows):
            out.setdefault(rows, g)
    return out


def glyph_names(tbl_path):
    names = {}
    for code, text in load_tbl(tbl_path).items():
        if len(code) == 2:
            names.setdefault(int.from_bytes(code, "little"), text)
    return names


class Sheet:
    """A block's tiles as one picture, `wide` tiles to a row (16, or what the block's layout uses);
    x past the right edge continues 16 px lower at the left."""

    def __init__(self, data, bpp, wide=16):
        self.bpp, self.tiles, self.wide = bpp, tile_pixels(data, bpp), wide
        self.W = 8 * wide
        self.height = -(-len(self.tiles) // wide) * 8

    def _at(self, x, y):
        y += 16 * (x // self.W)
        x %= self.W
        k = (y // 8) * self.wide + x // 8
        return (k, y % 8, x % 8) if 0 <= y < self.height and k < len(self.tiles) else None

    def get(self, x, y):
        at = self._at(x, y)
        return self.tiles[at[0]][at[1]][at[2]] if at else -1

    def set(self, x, y, v):
        at = self._at(x, y)
        if at:
            self.tiles[at[0]][at[1]][at[2]] = v

    def data(self):
        out = bytearray()
        for px in self.tiles:
            b = bytearray(8 * self.bpp)
            for y in range(8):
                for x in range(8):
                    for pl in range(self.bpp):
                        if px[y][x] >> pl & 1:
                            b[(pl // 2) * 16 + 2 * y + (pl % 2)] |= 0x80 >> x
            out += b
        return bytes(out)

    def cell(self, x, y, colour):
        return tuple(sum(1 << (11 - c) for c in range(12) if self.get(x + c, y + r) == colour) for r in range(12))


class TileGrid:
    """A label box built from listed tiles (rows of tile numbers), for labels whose halves the
    block stores apart (e.g. the top half in tiles 146-148, the bottom half in 149-151)."""

    def __init__(self, sheet, rows):
        self.sheet, self.rows = sheet, rows

    def _at(self, x, y):
        if 0 <= y < 8 * len(self.rows) and 0 <= x < 8 * len(self.rows[0]):
            return self.rows[y // 8][x // 8], y % 8, x % 8
        return None

    def get(self, x, y):
        at = self._at(x, y)
        return self.sheet.tiles[at[0]][at[1]][at[2]] if at else -1

    def set(self, x, y, v):
        at = self._at(x, y)
        if at:
            self.sheet.tiles[at[0]][at[1]][at[2]] = v


def find_runs(sheet, font, names, width=None):
    """-> list of (y, x, colour, [glyph codes]) runs of font characters 12 px apart."""
    width = width or sheet.W + 11
    W = width + 12
    bits = {}                                   # colour -> one int per row, bit W-1-x for pixel x
    for y in range(sheet.height):
        for x in range(W):
            v = sheet.get(x, y)
            if v > 0:
                row = bits.setdefault(v, [0] * sheet.height)
                row[y] |= 1 << (W - 1 - x)
    hits = {}
    for col, rows in bits.items():
        for y in range(sheet.height - 11):
            for x in range(width):
                shift = W - 12 - x
                cell = tuple((rows[y + r] >> shift) & 0xFFF for r in range(12))
                if cell[0] | cell[5] | cell[11] or any(cell):
                    g = font.get(cell)
                    if g is not None:
                        hits[(y, x)] = (col, g)
    runs, used = [], set()
    for (y, x), (col, g) in sorted(hits.items()):
        if (y, x) in used:
            continue
        codes, cx = [], x
        while hits.get((y, cx), (None,))[0] == col:
            codes.append(hits[(y, cx)][1])
            used.add((y, cx))
            cx += 12
        runs.append((y, x, col, codes))
    return runs


def load_letters(path, kind):
    """Letter sets -> {char: (width, [rows as strings])}. narrow/small/tiny: 'X @row' + rows of #/.;
    latin: a one-character line + 12 rows."""
    letters, cur = {}, None
    for line in open(path, encoding="utf-8").read().splitlines():
        if kind == "latin":
            if len(line) == 1:
                cur = letters[line] = []
            elif re.match(r"^[.#]{12}$", line) and cur is not None:
                cur.append(line)
            continue
        if not line.strip() or line.startswith("# "):
            cur = None
            continue
        m = re.match(r"^(\S+) @(\d+)$", line)
        if m:
            name = " " if m.group(1) == "space" else m.group(1)
            cur = letters[name] = [int(m.group(2))]
        elif cur is not None and re.match(r"^[.#]+$", line):
            cur.append(line)
    out = {}
    for ch, rows in letters.items():
        if kind == "latin":
            ink = [c for c in range(12) if any(r[c] == "#" for r in rows)]
            lo, hi = (ink[0], ink[-1]) if ink else (0, 3)
            out[ch] = (hi - lo + 1, [r[lo:hi + 1] for r in rows])
        else:
            top, body = rows[0], rows[1:]
            w = max((len(r) for r in body), default=3)
            out[ch] = (w, ["." * w] * top + body)
    if kind == "latin":
        out.setdefault(" ", (4, ["...."] * 12))     # a word space: 4 px plus the gaps
    return out


def text_bitmap(text, letters, gap):
    """-> (width, rows, spans) of the text, letters 'gap' px apart; spans = (first column, width) of each letter."""
    parts = [letters[ch] for ch in text]
    if not parts:
        return 0, [], []
    width = sum(w for w, _ in parts) + gap * (len(parts) - 1)
    spans, at = [], 0
    for w, _ in parts:
        spans.append((at, w))
        at += w + gap
    height = max(len(rows) for _, rows in parts)
    rows = ["" for _ in range(height)]
    for k, (w, glyph) in enumerate(parts):
        for r in range(height):
            rows[r] += (glyph[r] if r < len(glyph) else "." * w) + ("." * gap if k < len(parts) - 1 else "")
    return width, rows, spans


def draw_block(entry, rom_font, names, fonts, outdir):
    gid = entry["id"]
    data = open(os.path.join(outdir, "original", gid + ".bin"), "rb").read()
    sheet = Sheet(data, entry["bpp"], entry.get("tiles_wide", 16))
    runs = find_runs(sheet, rom_font, names)
    errors = []
    for lab in entry["labels"]:
        want = lab["jp"]
        box = TileGrid(sheet, lab["grid"]) if "grid" in lab else sheet
        if "at" in lab:                     # placed by hand: glyphs the artist changed do not match the font
            x, y = lab["at"]
            room, h = lab["w"], lab.get("h", 12)
            counts = {}
            for r in range(h):
                for c in range(room):
                    v = box.get(x + c, y + r)
                    if v >= 0:
                        counts[v] = counts.get(v, 0) + 1
            order = sorted(counts, key=counts.get, reverse=True)
            bg = lab.get("bg", order[0])
            col = lab.get("fg", order[1] if len(order) > 1 else order[0])
        else:
            spots = []
            for y, x, col, codes in runs:
                text = "".join(names.get(c, "?") for c in codes)
                k = text.find(want)
                while k >= 0:
                    spots.append((y, x + 12 * k, col))
                    k = text.find(want, k + 1)
            if not spots:
                errors.append(f"{gid}: {want} not found")
                continue
            near = lab.get("near", [spots[0][1], spots[0][0]])
            y, x, col = min(spots, key=lambda s: abs(s[1] - near[0]) + abs(s[0] - near[1]))
            room, h = 12 * len(want), 12
            others = {}
            for r in range(12):
                for c in range(room):
                    v = sheet.get(x + c, y + r)
                    if v != col and v >= 0:
                        others[v] = others.get(v, 0) + 1
            bg = lab.get("bg", max(others, key=others.get) if others else 0)
        letters, gap = fonts[lab["font"]]
        gap = lab.get("gap", gap)
        width, rows, spans = text_bitmap(lab["en"], letters, gap)
        if width > room:
            errors.append(f"{gid}: {lab['en']!r} is {width} px, {want} has {room}")
            continue
        clear = lab.get("clear", [col])
        holes = {(x + c, y + r) for r in range(h) for c in range(room) if box.get(x + c, y + r) in clear}
        if lab.get("fill") == "near":       # a picture behind the text: grow the colours around the holes inwards
            while holes:
                done = {}
                for px, py in holes:
                    near = [box.get(px + ox, py + oy) for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1))
                            if (px + ox, py + oy) not in holes and box.get(px + ox, py + oy) >= 0]
                    if near:
                        done[(px, py)] = max(near, key=near.count)
                if not done:
                    break
                for (px, py), v in done.items():
                    box.set(px, py, v)
                holes -= set(done)
        for px, py in holes:                # "checker": [a, b] refills a dithered box (a where x + y is even)
            box.set(px, py, lab["checker"][(px + py) % 2] if "checker" in lab else bg)
        align = lab.get("align")
        x0 = x + {"left": 0, "right": room - width}.get(align, (room - width) // 2) + lab.get("dx", 0)
        y0 = y + lab.get("dy", 0)
        ink = {(x0 + c, y0 + r) for r, line in enumerate(rows) for c, ch in enumerate(line) if ch == "#"}
        shade, shade_rows = lab.get("shade"), lab.get("shade_rows")
        for px, py in ink:
            if shade:                       # the colour by the pixel's column inside its letter
                s, w = next(sp for sp in spans if sp[0] <= px - x0 < sp[0] + sp[1])
                box.set(px, py, shade[(px - x0 - s) * len(shade) // w])
            elif shade_rows:                # the colour by the pixel's row (a top-to-bottom fade)
                box.set(px, py, shade_rows[py - y0])
            else:
                box.set(px, py, col)
        if "shadow" in lab:                 # a drop shadow one pixel right and down
            for px, py in ink:
                q = (px + 1, py + 1)
                if q not in ink and x <= q[0] < x + room and y <= q[1] < y + h:
                    box.set(q[0], q[1], lab["shadow"])
        filled = set(ink)
        for edge in ("border", "outline"):  # rings around the letters: "border" first, then "outline" around both
            if edge not in lab:
                continue
            ring = set()
            for px, py in filled:
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        q = (px + ox, py + oy)
                        if q not in filled and x <= q[0] < x + room and y <= q[1] < y + h and \
                                (box.get(*q) == bg or lab.get("fill") == "near"):
                            ring.add(q)
            for q in ring:
                box.set(q[0], q[1], lab[edge])
            filled |= ring
        print(f"{gid}: {want} at x {x}, y {y} (colour {col} on {bg}) -> {lab['en']!r}, {width} of {room} px")
    if errors:
        return errors
    new = sheet.data()
    os.makedirs(os.path.join(outdir, "edited"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "compare"), exist_ok=True)
    with open(os.path.join(outdir, "edited", gid + ".bin"), "wb") as f:
        f.write(new)
    grey = [(v * 255 // ((1 << entry["bpp"]) - 1),) * 3 for v in range(1 << entry["bpp"])]
    pics = []
    for blob in (data, new):
        s = Sheet(blob, entry["bpp"], sheet.wide)
        pics.append([[grey[s.get(x, y)] for x in range(s.W)] for y in range(s.height)])
    write_png(os.path.join(outdir, "edited", gid + ".png"), pics[1])
    write_png(os.path.join(outdir, "compare", gid + ".png"), pics[0] + [[(160, 30, 30)] * sheet.W] * 4 + pics[1])
    changed = sum(a != b for a, b in zip(data, new))
    print(f"{gid}: {changed} bytes changed of {len(data)} -> edited/{gid}.bin")
    return []


def edit_map(entry, outdir):
    """A screen layout block (16-bit tile map entries, 32 to a row): change the tile number of the listed
    entries, keeping their palette and flip bits. Each edit says which tile it expects to replace."""
    gid = entry["id"]
    data = bytearray(open(os.path.join(outdir, "original", gid + ".bin"), "rb").read())
    errors = []
    for e in entry["map_edits"]:
        olds, tiles = e["old"], e["tile"]
        if not isinstance(olds, list):
            olds, tiles = [olds], [tiles]
        for k, (old, tile) in enumerate(zip(olds, tiles)):
            at = (e["y"] * 32 + e["x"] + k) * 2
            word = int.from_bytes(data[at:at + 2], "little")
            if word & 0x3FF != old:
                errors.append(f"{gid}: entry {e['x'] + k},{e['y']} is tile {word & 0x3FF}, not {old}")
                continue
            data[at:at + 2] = ((word & ~0x3FF) | tile).to_bytes(2, "little")
        print(f"{gid}: entries {e['x']}-{e['x'] + len(olds) - 1},{e['y']} tiles {olds} -> {tiles}")
    if not errors:
        os.makedirs(os.path.join(outdir, "edited"), exist_ok=True)
        with open(os.path.join(outdir, "edited", gid + ".bin"), "wb") as f:
            f.write(data)
    return errors


def main():
    args = sys.argv[1:]
    if len(args) >= 5 and args[0] == "find":
        rom = open(args[1], "rb").read()
        font, names = game_font(rom), glyph_names(args[2])
        sheet = Sheet(open(args[3], "rb").read(), int(args[4]))
        for y, x, col, codes in find_runs(sheet, font, names):
            print(f"y {y:3d}  x {x:3d}  colour {col:2d}  {''.join(names.get(c, '?') for c in codes)}")
    elif len(args) >= 5 and args[0] == "draw":
        rom = open(args[1], "rb").read()
        font, names = game_font(rom), glyph_names(args[2])
        build = os.path.join(WORK, "04_build", "output")
        fonts = {"narrow": (load_letters(os.path.join(build, "narrow-font.txt"), "narrow"), 1),
                 "latin": (load_letters(os.path.join(build, "latin-font.txt"), "latin"), 2)}
        extra = os.path.join(args[4], "gfx-fonts.txt")
        if os.path.exists(extra):
            sets = open(extra, encoding="utf-8").read().split("\n== ")
            for part in sets[1:]:
                name, _, body = part.partition("\n")
                tmp = os.path.join(args[4], f".{name.strip()}.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(body)
                fonts[name.strip()] = (load_letters(tmp, "narrow"), 1)
                os.remove(tmp)
        entries = json.load(open(args[3], encoding="utf-8"))
        errors = []
        for entry in entries:
            if not args[5:] or entry["id"] in args[5:]:
                if entry.get("labels"):
                    errors += draw_block(entry, font, names, fonts, args[4])
                if entry.get("map_edits"):
                    errors += edit_map(entry, args[4])
        if errors:
            sys.exit("\n".join(errors))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
