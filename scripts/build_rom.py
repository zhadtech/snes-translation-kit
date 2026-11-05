"""Build the patched ROM: pack translated blocks into free space and fix what points to them.

usage: build_rom.py ROM EXTRACT_DIR TRANSLATED_DIR BUILD_MAP OUT_ROM

EXTRACT_DIR holds charset.tbl, blocks.json and pointers.json (stage 02).
BUILD_MAP (JSON) says, per bank, which old block areas and free ranges may be reused, and lists
the units to place (whole blocks or line ranges, packed in order with FFFF ends, no padding).
A unit may carry "head"/"tail" bytes: that many original bytes from just before its first line
or just after its last line's FFFF, copied along (script scenes: an empty start piece, the end word).
"room_after" checks that each line has that many bytes before its bank ends (fixed-size copies).
After placing, it rewrites:
  - every pointer table entry (pointers.json) that points at a moved line,
  - every 2-byte pointer listed in "refs" (each must hold the old address of a line in its block),
  - every 3-byte pointer listed in "refs3" (it may point inside a line or a unit's head; the byte
    distance is kept, and the bytes before it must be unchanged unless the line is in "mid_line_ok"),
  - every "msg_tables" entry (a 3-byte base pointer + 2-byte offsets from it, main dialogue),
  - every byte listed in "bytes" (each must hold its "old" value),
then does the "copies" (byte ranges copied after the rewrites) and fixes the header checksum.
Lines with no `en` (or skipped) keep their Japanese bytes. Blocks in "fixed_in_place" are
written slot by slot like insert_text.py (optionally with another block's text); "slot_tables"
writes a fixed-slot block's English to a new table with a wider stride. "narrow" turns the lines of
the listed blocks into pairs of narrow letters (two per glyph cell), drawn into the listed glyph
slots and centred in each block's field. "prop" sets the listed lines in the full-size Latin letters by
their own widths and cuts them into new 12-px glyphs (no gaps around thin letters). "code_text" writes the glyph codes of each listed block's
lines into the instruction operands the dump recorded for them. "latin" redraws the font's Latin
glyphs from a 12 x 12 art file. "graphics" packs the picture-text blocks redrawn in stage 03b
(gfx-map.json and edited/Gxx.bin in that folder) and writes each over its original. "narrow_names" gives name fields narrow names: display
name lists rewritten in place, and new tables for the readers named in "refs". The original ROM is
never changed.
"""
import json
import os
import re
import sys

from gfx_pack import PACK
from gfx_unpack import UNPACK
from narrow_text import PIECE_LEAD, SCRIPT_LEAD, TOKEN, even, name_before, split_lead, wrap
from tbl import encode, load_tbl

FONT_BASE = 0x0A8000          # 12 x 12, 1bpp, 24 bytes per glyph (2 bytes per row, left 12 bits)
BLANK_GLYPH = 0x003E          # the space glyph


def num(s):
    return int(s, 16) if isinstance(s, str) else s


def load_narrow_font(path):
    """Narrow letters: {char: [12 rows of 5-bit ints]}. See stages/04_build/output/narrow-font.txt."""
    font, cur, row = {}, None, 0
    for line in open(path, encoding="utf-8").read().splitlines():
        if not line.strip() or line.startswith("# "):
            cur = None
            continue
        m = re.match(r"^(\S+) @(\d+)$", line)
        if m:
            cur = font[" " if m.group(1) == "space" else m.group(1)] = [0] * 12
            row = int(m.group(2))
        elif cur is not None and re.match(r"^[.#]{5}$", line):
            cur[row] = int(line.replace(".", "0").replace("#", "1"), 2)
            row += 1
        else:
            raise ValueError(f"{path}: bad line {line!r}")
    return font


def load_latin_font(path):
    """Full-size letters: {char: [12 rows of 12-bit ints]}. A one-character line names a glyph and the
    next 12 lines of '.'/'#' draw it. See stages/04_build/output/latin-font.txt."""
    font, cur = {}, None
    for line in open(path, encoding="utf-8").read().splitlines():
        if re.match(r"^[.#]{12}$", line) and cur is not None:
            cur.append(int(line.replace(".", "0").replace("#", "1"), 2))
        elif len(line) == 1:
            cur = font[line] = []
        elif line.strip() and not line.startswith("# "):
            raise ValueError(f"{path}: bad line {line!r}")
    bad = [ch for ch, rows in font.items() if len(rows) != 12]
    if bad:
        raise ValueError(f"{path}: glyphs without 12 rows: {bad}")
    return font


def pair_glyph(font, pair):
    """24 font bytes for two narrow letters side by side (columns 0-4 and 6-10)."""
    a, b = font[pair[0]], font[pair[1]]
    return b"".join(((a[r] << 7 | b[r] << 1) << 4).to_bytes(2, "big") for r in range(12))


def prop_cells(text, font, gap, space, centre=None):
    """Full-size letters set by their ink width, `gap` px apart (a space is `space` px), from the first
    letter's own left edge (or centred in `centre` cells), cut into 12-px glyph cells.
    -> list of cells, each 12 rows of 12-bit ints."""
    cols, start = [], None                  # one int per pixel column: bit r = row r
    for k, ch in enumerate(text):
        if k:
            cols += [0] * gap
        if ch == " ":
            cols += [0] * space
            continue
        rows = font[ch]
        ink = [c for c in range(12) if any(r >> (11 - c) & 1 for r in rows)] or [0, 3]
        if start is None:
            start = ink[0]
            cols = [0] * start + cols
        cols += [sum(1 << r for r in range(12) if rows[r] >> (11 - c) & 1) for c in range(ink[0], ink[-1] + 1)]
    if centre:
        cols = cols[start or 0:]
        cols = [0] * ((12 * centre - len(cols)) // 2) + cols
        cols += [0] * (12 * centre - len(cols))
    cols += [0] * (-len(cols) % 12)
    return [[sum(1 << (11 - c) for c in range(12) if cols[12 * k + c] >> r & 1) for r in range(12)]
            for k in range(len(cols) // 12)]


def narrow_lines(lines, fields, font, slots, heads=None, pad_cells=None, table=None, leads=None, flow=()):
    """Encode label lines as letter pairs. -> ({line id: bytes}, {glyph code: pair}, errors).
    Each label is centred in its block's field (pixels) with FFFE, which moves the pen 4 px.
    A block in `heads` instead starts each line with a layout byte chosen by its number of cells;
    a block whose field is None gets the letters only (names: the game lays them out itself).
    A block in `pad_cells` gets blank glyphs after the letters up to that many cells, so the game
    picks its layout for that many (left-aligned lists).
    Control words at the start of a line ({XXXX}, e.g. a screen position) are kept as they are; a block
    in `leads` keeps what its regex matches instead (script commands). In a block in `flow` (sentences),
    an odd-length text drops a trailing space rather than adding one, so pieces join without a gap."""
    heads, pad_cells, leads = heads or {}, pad_cells or {}, leads or {}
    out, used, errors = {}, {}, []
    for ln in lines:
        lead_re = leads.get(ln["block"], r"(?:\{[0-9A-F]{4}\})*")
        lead, text = re.match(f"({lead_re})(.*)", ln.get("en") or "", re.S).groups()
        lead = encode(lead, table) if lead else b""
        items = []                          # letter pairs, and name tokens kept as they are
        for k, part in enumerate(TOKEN.split(text)):
            if k:
                items.append(TOKEN.findall(text)[k - 1])
            part = even(part) if ln["block"] in flow else part + " " * (len(part) % 2)
            items += [part[i:i + 2] for i in range(0, len(part), 2)]
        pairs = [p for p in items if not TOKEN.fullmatch(p)]
        bad = sorted({ch for ch in TOKEN.sub("", text) if ch not in font})
        width = 12 * len(pairs)
        field = fields[ln["block"]] or width
        if bad or width > field:
            errors.append(f"{ln['id']}: {'no narrow letter for ' + repr(bad) if bad else f'{width} px > field'}")
            continue
        codes = []
        for p in items:
            if TOKEN.fullmatch(p):
                codes.append(int.from_bytes(encode(p, table), "little"))
                continue
            if p == "  ":
                codes.append(BLANK_GLYPH)
                continue
            code = next((c for c, q in used.items() if q == p), None)
            if code is None:
                if len(used) == len(slots):
                    errors.append(f"{ln['id']}: out of glyph slots")
                    break
                code = slots[len(used)]
                used[code] = p
            codes.append(code)
        codes += [BLANK_GLYPH] * (pad_cells.get(ln["block"], 0) - len(codes))
        body = b"".join(c.to_bytes(2, "little") for c in codes)
        if ln["block"] in heads:
            out[ln["id"]] = lead + bytes([heads[ln["block"]][str(len(codes))]]) + body
        else:
            out[ln["id"]] = lead + b"\xFE\xFF" * ((field - width) // 8) + body
    return out, used, errors


def addr16(off):
    return 0x8000 + off % 0x8000


def narrow_name_jobs(B, orig, names, errors):
    """Work out the narrow name for every entry of the listed name lists and copied tables.
    An entry's old target is a line start (its English, or its "short" form when longer than the
    job's letter limit, or the job's "short_key" field after that) or a point inside a line
    ("Bxx-nnn+delta", looked up in "special"). "odd_lead": a name with an odd number of letters gets a
    space before it, so it ends on a whole cell and the sentence text after it joins without a gap."""
    spans = sorted((ln["offset"], ln["offset"] + ln["max_bytes"] + 2, i)
                   for i, ln in B.lines.items() if ln["block"] in names["blocks"])
    jobs = []
    for spec in names.get("lists", []) + names.get("tables", []):
        p, n, limit = num(spec.get("at") or spec["copy_of"]), spec["count"], spec["letters"]
        job = dict(spec, kind="list" if "at" in spec else "table", start=p, texts=[])
        for k in range(n):
            off = int.from_bytes(orig[p + 2 * k:p + 2 * k + 2], "little") - 0x8000
            hit = next(((a, i) for a, b, i in spans if a <= off < b), None)
            if hit is None:
                errors.append(f"narrow names {hex(p)} entry {k}: no line at {hex(off)}")
                continue
            ln, key = B.lines[hit[1]], hit[1] + (f"+{off - hit[0]}" if off != hit[0] else "")
            text = names.get("special", {}).get(key)
            if text is None and key == hit[1]:
                text = next((t for t in (ln["en"], ln.get("short"), ln.get(spec.get("short_key", "short")))
                             if t and len(t) <= limit), None)
            if not text or len(text) > limit:
                errors.append(f"narrow names {hex(p)} entry {k} ({key}): no name of {limit} letters or fewer")
                continue
            text += spec.get("suffix", "")     # e.g. "!": a name that ends its message carries the mark itself
            job["texts"].append(" " + text if spec.get("odd_lead") and len(text) % 2 else text)
        for r in spec.get("refs", []):
            want = num(spec.get("refs_old", {}).get(r, hex(addr16(p))))    # a reader of a parallel table
            if int.from_bytes(orig[num(r):num(r) + 2], "little") != want:
                errors.append(f"narrow names: operand {r} does not hold ${want:04X}")
        jobs.append(job)
    return jobs


class Builder:
    def __init__(self, rom, table, blocks, tdir):
        self.rom = rom
        self.table = table
        self.blocks = blocks
        self.lines = {}      # line id -> line dict (with "block")
        self.order = {}      # block id -> [line ids]
        for bid in blocks:
            path = os.path.join(tdir, f"{bid}.json")
            if not os.path.exists(path):
                continue
            data = json.load(open(path, encoding="utf-8"))
            self.order[bid] = []
            for ln in data["lines"]:
                ln["block"] = bid
                self.lines[ln["id"]] = ln
                self.order[bid].append(ln["id"])
        self.new = {}        # line id -> new file offset
        self.override = {}   # line id -> bytes (narrow labels)
        self.odd = {}        # "line id/odd" -> new file offset of a line's odd-name version (7g)

    def line_bytes(self, ln):
        if ln["id"] in self.override:
            return self.override[ln["id"]]
        if ln.get("en") and not ln.get("skip"):
            return encode(ln["en"], self.table)
        return bytes(self.rom[ln["offset"]:ln["offset"] + ln["max_bytes"]])

    def unit_ids(self, spec):
        if ".." in spec:
            a, b = spec.split("..")
            first, last = a.split("-")[0], b.split("-")[0]
            ids = [i for bid in sorted(self.order) if first <= bid <= last for i in self.order[bid]]
            return ids[ids.index(a):ids.index(b) + 1]
        if "-" in spec:
            return [spec]
        return list(self.order[spec])

    def old_lookup(self, bid):
        """2-byte address -> line id, for a block's original lines."""
        return {addr16(self.lines[i]["offset"]): i for i in self.order[bid]}


def take(free, size, at=None):
    """Carve `size` bytes out of the free list. at=None: first fit. Returns the offset."""
    for k, (a, b) in enumerate(free):
        start = a if at is None else at
        if a <= start and start + size <= b:
            free[k:k + 1] = [r for r in ((a, start), (start + size, b)) if r[1] > r[0]]
            return start
        if at is not None and a <= at < b:
            break
    return None


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    rom_path, xdir, tdir, map_path, out_path = sys.argv[1:]
    if os.path.abspath(rom_path) == os.path.abspath(out_path):
        sys.exit("refusing to overwrite the original ROM")
    orig = open(rom_path, "rb").read()
    rom = bytearray(orig)
    table = load_tbl(os.path.join(xdir, "charset.tbl"))
    blocks = {b["id"]: b for b in json.load(open(os.path.join(xdir, "blocks.json")))}
    tables = json.load(open(os.path.join(xdir, "pointers.json")))["tables"]
    bmap = json.load(open(map_path, encoding="utf-8"))
    B = Builder(orig, table, blocks, tdir)
    errors = []

    # 0. Narrow labels: letter pairs drawn into reused glyph slots (kanji no known text shows).
    # Narrow names (see 4d) are encoded in the same pass, after the labels.
    narrow, glyphs = bmap.get("narrow"), {}
    names = bmap.get("narrow_names")
    name_jobs = narrow_name_jobs(B, orig, names, errors) if names else []
    if narrow:
        font = load_narrow_font(os.path.join(os.path.dirname(map_path), narrow["font"]))
        only = narrow.get("only", {})      # block -> [first id, last id]: just those lines are narrow
        labels = [B.lines[i] for bid in narrow["fields"] for i in B.order[bid]
                  if bid not in only or only[bid][0] <= i <= only[bid][1]]
        # Sentences in letter pairs ("narrow_text", see narrow_text.py): only the "active" blocks.
        ntext = bmap.get("narrow_text", {})
        active = set(ntext.get("active", []))
        boxes = {b: c for b, c in ntext.get("box", {}).items() if b in active}
        script = ntext.get("script", {})
        scripts = [b for b in script.get("blocks", []) if b in active]
        skip = set(script.get("skip", [])) | {i for c in boxes.values() for i in c.get("skip", [])}
        pieces = {i for c in boxes.values() for i in c.get("label_lines", [])}
        for bid in list(boxes) + scripts:
            for i in B.order[bid]:
                ln = dict(B.lines[i])
                if i in pieces and ln.get("en"):    # joined by code (level-up): pairs as they are, no wrap
                    labels.append(ln)
                    continue
                if i in skip or not ln.get("en") or ln.get("skip"):
                    continue
                if bid in boxes:
                    box = boxes[bid]
                    lead, body = split_lead(ln["en"], PIECE_LEAD if box.get("pieces") else "")
                    laid, _, errs = wrap(body, dict(box, rows=None) if box.get("pieces") else box, ln.get("src"),
                                         ln.get("plain"), name_before(box, i))
                    ln["en"] = lead + laid
                    errors += [f"{i}: {e} (narrow text)" for e in errs]
                    if ln.get("en_odd"):        # the line after a name with an odd number of letters (see 7g)
                        odd, _, errs = wrap(ln["en_odd"], box, ln.get("src"), True, name_before(box, i))
                        labels.append(dict(ln, id=i + "/odd", en=odd))
                        errors += [f"{i}/odd: {e} (narrow text)" for e in errs]
                labels.append(ln)
        texts = sorted({text for job in name_jobs for text in job["texts"]})
        labels += [{"id": "name:" + text, "en": text, "block": "_names"} for text in texts]
        fields = dict(narrow["fields"], _names=None, **{bid: None for bid in list(boxes) + scripts})
        leads = {bid: SCRIPT_LEAD for bid in scripts}
        leads.update({bid: PIECE_LEAD for bid, c in boxes.items() if c.get("pieces")})
        B.override, glyphs, errs = narrow_lines(labels, fields, font, [num(s) for s in narrow["slots"]],
                                                narrow.get("heads"), narrow.get("pad_cells"), table,
                                                leads, set(boxes) | set(scripts))
        name_bytes = {text: B.override.pop("name:" + text, b"") for text in texts}
        errors += errs

    # 0b. Proportional labels: a line set in the full-size Latin letters by their own widths (no empty
    # 12-px cells around thin letters), cut into 12-px glyphs. The glyphs go into the narrow pool's
    # slots from its end, past the ones the letter pairs took. Leading control words are kept.
    prop, prop_glyphs = bmap.get("prop"), {}
    if prop:
        lfont = load_latin_font(os.path.join(os.path.dirname(map_path), prop["font"]))
        pool = [num(s) for s in reversed(narrow["slots"]) if num(s) not in glyphs]
        seen = {}
        for i in prop["lines"]:
            ln = B.lines[i]
            lead, text = re.match(r"((?:\{[0-9A-F]{4}\})*)(.*)", ln["en"], re.S).groups()
            bad = sorted({ch for ch in text if ch != " " and ch not in lfont})
            if bad:
                errors.append(f"{i}: no Latin letter for {bad} (prop)")
                continue
            codes = []
            for cell in prop_cells(text, lfont, prop.get("gap", 2), prop.get("space", 4), prop.get("centre", {}).get(i)):
                key = tuple(cell)
                if not any(cell):
                    codes.append(BLANK_GLYPH)
                elif key in seen:
                    codes.append(seen[key])
                elif not pool:
                    errors.append(f"{i}: out of glyph slots (prop)")
                    break
                else:
                    seen[key] = pool.pop(0)
                    prop_glyphs[seen[key]] = cell
                    codes.append(seen[key])
            data = (encode(lead, table) if lead else b"") + b"".join(c.to_bytes(2, "little") for c in codes)
            if not ln.get("repoint") and len(data) > ln["max_bytes"]:
                errors.append(f"{i}: {len(data)} bytes > {ln['max_bytes']} in place (prop)")
            B.override[i] = data
        print(f"glyph slots: {len(glyphs)} letter pairs, {len(prop_glyphs)} proportional, "
              f"{len(narrow['slots']) - len(glyphs) - len(prop_glyphs)} left")

    # 1. Free space per bank: old block areas + listed ranges, minus copy targets.
    free = {}
    for bank, spec in bmap["banks"].items():
        rngs = [(num(a), num(b)) for a, b in spec["free"]]
        rngs += [(num(blocks[b]["start"]), num(blocks[b]["end"])) for b in spec["reuse"]]
        merged = []
        for a, b in sorted(rngs):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        free[bank] = merged
    reserved = [(c["to"], c["size"]) for c in bmap.get("copies", [])]
    reserved += [(s["to"], s["stride"] * len(B.order[s["block"]])) for s in bmap.get("slot_tables", [])]
    for at, size in reserved:
        to = num(at)
        for bank in free:
            for a, b in free[bank]:
                if a <= to < b:
                    if take(free[bank], size, at=to) is None:
                        errors.append(f"target {at} (+{size}) is not free")
    for bank, rngs in free.items():
        for a, b in rngs:
            rom[a:b] = b"\xFF" * (b - a)

    # 2. Place units (pinned first), packed in order with FFFF ends.
    units = sorted(bmap["units"], key=lambda u: not u.get("pin"))
    report = []
    heads = []          # (old start, old end, new start) of each unit's head bytes
    for u in units:
        ids = B.unit_ids(u["lines"])
        first, last = B.lines[ids[0]], B.lines[ids[-1]]
        head_at = first["offset"] - u.get("head", 0)
        tail_at = last["offset"] + last["max_bytes"] + 2
        data = bytearray(orig[head_at:first["offset"]])
        offs = []
        for i in ids:
            offs.append(len(data))
            data += B.line_bytes(B.lines[i]) + b"\xFF\xFF"
        extra = []                      # odd-name versions (7g) follow the unit's lines
        for i in ids:
            if i + "/odd" in B.override:
                extra.append((i + "/odd", len(data)))
                data += B.override[i + "/odd"] + b"\xFF\xFF"
        data += orig[tail_at:tail_at + u.get("tail", 0)]
        at = head_at if u.get("pin") else None
        start = take(free[u["bank"]], len(data), at=at)
        if start is None:
            errors.append(f"unit {u['lines']}: no room for {len(data)} bytes in bank {u['bank']}")
            continue
        if start // 0x8000 != (start + len(data) - 1) // 0x8000:
            errors.append(f"unit {u['lines']} crosses a bank edge")
        # "room_after": the game reads this many bytes from each line start (a fixed-size copy),
        # so they must stay inside the bank.
        for i, o in zip(ids, offs):
            if (start + o) % 0x8000 + u.get("room_after", 0) > 0x8000:
                errors.append(f"{i}: less than {u['room_after']} bytes before the bank ends")
        rom[start:start + len(data)] = data
        for i, o in zip(ids, offs):
            B.new[i] = start + o
        for i, o in extra:
            B.odd[i] = start + o
        heads.append((head_at, first["offset"], start))
        report.append((u["bank"], start, len(data), u["lines"]))

    # 3. Pointer tables: rewrite entries that point at moved lines.
    # An entry may also point at an empty string (a lone FFFF) right after line X's end;
    # it then gets X's new end marker, which is also an empty string.
    by_old, empty_after = {}, {}
    for i, ln in B.lines.items():
        bank, end = ln["offset"] // 0x8000, ln["offset"] + ln["max_bytes"]
        by_old[(bank, addr16(ln["offset"]))] = i
        if "record_bytes" not in blocks[ln["block"]] and orig[end + 2:end + 4] == b"\xFF\xFF":
            empty_after[(bank, addr16(end + 2))] = i

    def new_ptr(bank, val):
        """New 2-byte value for an old pointer, None if not a known target, False if unmoved."""
        if (bank, val) in by_old:
            lid = by_old[(bank, val)]
            return addr16(B.new[lid]) if lid in B.new else False
        if (bank, val) in empty_after:
            lid = empty_after[(bank, val)]
            if lid not in B.new:
                return False
            return addr16(B.new[lid] + len(B.line_bytes(B.lines[lid])))
        return None

    for t in tables:
        if t.get("kind") != "text":
            continue
        o, bank = num(t["offset"]), num(t["bank_base"]) // 0x8000
        for k in range(t["entries"]):
            p = o + k * t["entry_size"]
            val = new_ptr(bank, int.from_bytes(orig[p:p + 2], "little"))
            if val is None:
                if any(i in B.new for x in t["points_to"] for i in B.order.get(x, [])):
                    errors.append(f"table {t['offset']} entry {k}: "
                                  f"${int.from_bytes(orig[p:p + 2], 'little'):04X} is not a line start")
            elif val is not False:
                rom[p:p + 2] = val.to_bytes(2, "little")

    # 4. Listed 2-byte pointers (code operands, data records).
    for r in bmap.get("refs", []):
        look = B.old_lookup(r["block"])
        for at in r["at"]:
            p = num(at)
            val = int.from_bytes(orig[p:p + 2], "little")
            lid = look.get(val)
            if lid is None:
                errors.append(f"ref {at}: ${val:04X} is not a line start in {r['block']}")
            elif lid in B.new:
                rom[p:p + 2] = addr16(B.new[lid]).to_bytes(2, "little")

    # 4b. Listed 3-byte pointers (scene tables). The target keeps its byte distance from the
    # start of its line (or of its unit's head), so a scene may start after a line's command word.
    mid_ok = set(bmap.get("mid_line_ok", []))
    moved = [(B.lines[i]["offset"], B.lines[i]["max_bytes"] + 2, i) for i in B.new]

    def new_target(t):
        for a, b, start in heads:
            if a <= t < b:
                return start + (t - a)
        for o, size, i in moved:
            if o <= t < o + size:
                d, nb = t - o, B.line_bytes(B.lines[i])
                if d % 2 or d > len(nb):
                    return f"distance {d} does not fit {i}"
                if i not in mid_ok and orig[o:o + d] != nb[:d]:
                    return f"points {d} bytes into {i}, past changed text"
                return B.new[i] + d
        return "target is not in a moved unit"

    for at in bmap.get("refs3", []):
        p = num(at)
        bank = orig[p + 2]
        t = (bank & 0x7F) * 0x8000 + int.from_bytes(orig[p:p + 2], "little") - 0x8000
        new = new_target(t)
        if isinstance(new, str):
            errors.append(f"ref3 {at} (${bank:02X}:{addr16(t):04X}): {new}")
        else:
            rom[p:p + 3] = addr16(new).to_bytes(2, "little") + bytes([bank & 0x80 | new // 0x8000])

    # 4c. Message tables: a base pointer and `count` 2-byte offsets from it. The base is either 3
    # bytes at "at" with the offsets right after (main dialogue), or code operands: "base_addr"
    # (2-byte) and "base_bank" (1-byte) offsets, every copy rewritten, with the offsets at "offsets"
    # (boarding lines). The game adds an offset to the base address with no carry into the bank, so
    # every message must land in the base's bank, at or after the base. Offsets the game never
    # reads ("stale": all of them, "stale_entries": some) are set to 0, the table's first message.
    for m in bmap.get("msg_tables", []):
        name, n = m.get("at") or m["offsets"], m["count"]
        if "at" in m:
            p = num(m["at"])
            addr_at, bank_at, offs_at = [p], [p + 2], p + 3
        else:
            addr_at, bank_at = [num(a) for a in m["base_addr"]], [num(a) for a in m["base_bank"]]
            offs_at = num(m["offsets"])
        if len({bytes(orig[a:a + 2]) for a in addr_at} | {bytes([orig[b], 0]) for b in bank_at}) != 2:
            errors.append(f"msg table {name}: the base copies differ")
            continue
        bank = orig[bank_at[0]]
        old_base = (bank & 0x7F) * 0x8000 + int.from_bytes(orig[addr_at[0]:addr_at[0] + 2], "little") - 0x8000
        base = new_target(old_base)
        if isinstance(base, str):
            errors.append(f"msg table {name} base: {base}")
            continue
        for a in addr_at:
            rom[a:a + 2] = addr16(base).to_bytes(2, "little")
        for b in bank_at:
            rom[b] = bank & 0x80 | base // 0x8000
        stale = set(range(n)) if m.get("stale") else set(m.get("stale_entries", []))
        for k in range(n):
            q = offs_at + 2 * k
            t = base if k in stale else new_target(old_base + int.from_bytes(orig[q:q + 2], "little"))
            if isinstance(t, str) or t < base or t // 0x8000 != base // 0x8000:
                errors.append(f"msg table {name} entry {k}: {t if isinstance(t, str) else 'not in the base bank'}")
                continue
            rom[q:q + 2] = (t - base).to_bytes(2, "little")

    # 4d. Narrow names (bank $80, read through bank $00): each name once per layout, then the
    # display name lists rewritten in place and new tables for the readers listed in "refs". A table with
    # "bank" lives in that bank instead, and "suffix" is added to each name (for code of our own, see 7h).
    # "pad_cells" centres a name in that many cells with blank glyphs, so the game always picks
    # its layout for that many characters ("lead_min" blank cells at least, when there is room).
    # "gap_centre" (a field width in px) instead centres it with FFFE (4 px each, at least one),
    # for readers that draw with the label routine.
    if name_jobs and narrow:
        blank = bytes.fromhex(names.get("pad_code", "003E"))[::-1]
        name_at = {}

        def layout(job):        # a job with "bank" keeps its names and table in that bank (read with a long address)
            return job.get("pad_cells", 0), job.get("gap_centre"), job.get("lead_min", 0), job.get("bank", "80")

        for job in name_jobs:
            if len(job["texts"]) != job["count"]:
                continue
            pad, gap, lead_min, bank = layout(job)
            for text in job["texts"]:
                if (text, layout(job)) in name_at:
                    continue
                cells = len(name_bytes[text]) // 2
                if gap:
                    data = b"\xFE\xFF" * max(1, round((gap - 12 * cells) / 8)) + name_bytes[text]
                else:
                    lead = max(pad - cells, 0) // 2
                    lead = max(lead, min(lead_min, pad - cells)) if pad > cells else lead
                    data = blank * lead + name_bytes[text] + blank * max(pad - cells - lead, 0)
                at = take(free[bank], len(data) + 2)
                if at is None:
                    errors.append(f"narrow name {text!r}: no room in bank {bank}")
                    break
                rom[at:at + len(data) + 2] = data + b"\xFF\xFF"
                name_at[text, layout(job)] = at
        for job in name_jobs:
            pad = layout(job)
            if len(job["texts"]) != job["count"] or not all((t, pad) in name_at for t in job["texts"]):
                continue
            at = job["start"] if job["kind"] == "list" else take(free[pad[3]], 2 * job["count"])
            if at is None:
                errors.append(f"narrow name table {job['copy_of']}: no room in bank {pad[3]}")
                continue
            for k, text in enumerate(job["texts"]):
                rom[at + 2 * k:at + 2 * k + 2] = addr16(name_at[text, pad]).to_bytes(2, "little")
            for r in job.get("refs", []):
                rom[num(r):num(r) + 2] = addr16(at).to_bytes(2, "little")
            job["new_at"] = at

    # 5. Byte patches (bank bytes, copy limits).
    for b in bmap.get("bytes", []):
        p, old, new = num(b["at"]), bytes.fromhex(b["old"]), bytes.fromhex(b["new"])
        if orig[p:p + len(old)] != old:
            errors.append(f"byte {b['at']}: expected {b['old']}, found {orig[p:p + len(old)].hex().upper()}")
        else:
            rom[p:p + len(new)] = new

    # 6. Copies (after the rewrites, so they carry the new pointers).
    for c in bmap.get("copies", []):
        a, to, size = num(c["from"]), num(c["to"]), c["size"]
        rom[to:to + size] = rom[a:a + size]

    # 7. Fixed-slot blocks written in place. An entry {"block": X, "text_from": Y} fills X's slots
    # (with X's pad) from Y's English, slot by slot.
    for spec in bmap.get("fixed_in_place", []):
        bid, src = (spec, spec) if isinstance(spec, str) else (spec["block"], spec["text_from"])
        pad = bytes.fromhex(blocks[bid]["pad"])
        for i, j in zip(B.order[bid], B.order[src]):
            ln, text = B.lines[i], B.lines[j].get("en")
            if not text:
                continue
            data = B.override.get(j) or encode(text, table)   # narrow labels keep their letter pairs
            if len(data) > ln["max_bytes"]:
                errors.append(f"{i}: {len(data)} bytes > {ln['max_bytes']} (fixed slot)")
                continue
            body = data + pad * ((ln["max_bytes"] - len(data)) // len(pad))
            rom[ln["offset"]:ln["offset"] + ln["max_bytes"]] = body

    # 7b. Slot tables: a fixed-slot block's English written to a new table with a wider stride.
    # The code that reads it is pointed there through "bytes". Narrow labels keep their letter pairs.
    for s in bmap.get("slot_tables", []):
        to, stride, pad = num(s["to"]), s["stride"], bytes.fromhex(s["pad"])
        for k, i in enumerate(B.order[s["block"]]):
            data = B.override.get(i) or encode(B.lines[i]["en"], table)
            if len(data) > stride:
                errors.append(f"{i}: {len(data)} bytes > stride {stride} (slot table)")
                continue
            rom[to + k * stride:to + (k + 1) * stride] = data + pad * ((stride - len(data)) // len(pad))

    # 7d. Code text: a line written by code one glyph at a time (LDA/LDX/LDY #code). Each glyph code
    # of the English goes into the next operand listed in the line; the rest get blanks.
    for bid in bmap.get("code_text", []):
        for i in B.order[bid]:
            ln = B.lines[i]
            ops = [num(a) for a in ln["operands"]]
            data = B.override.get(i) or encode(ln["en"], table)
            codes = [data[k:k + 2] for k in range(0, len(data), 2)]
            if len(codes) > len(ops):
                errors.append(f"{i}: {len(codes)} glyphs > {len(ops)} operands (code text)")
                continue
            if any(orig[a - 1] not in (0xA0, 0xA2, 0xA9) for a in ops) or \
                    b"".join(orig[a:a + 2] for a in ops) != encode(ln["src"], table):
                errors.append(f"{i}: operands do not hold the dumped text (code text)")
                continue
            codes += [BLANK_GLYPH.to_bytes(2, "little")] * (len(ops) - len(codes))
            for a, c in zip(ops, codes):
                rom[a:a + 2] = c

    # 7e. Latin letters redrawn (higher baseline): each glyph replaces the font glyph that the
    # table gives for its character. Japanese glyphs are not touched.
    if bmap.get("latin"):
        for ch, rows in load_latin_font(os.path.join(os.path.dirname(map_path), bmap["latin"]["font"])).items():
            g = int.from_bytes(encode(ch, table), "little")
            if g >= 0x0057:          # あ is 0x0057: everything from there on is Japanese
                errors.append(f"latin font: {ch!r} is glyph {g:04X}, not a Latin glyph")
                continue
            rom[FONT_BASE + 24 * g:FONT_BASE + 24 * (g + 1)] = b"".join((r << 4).to_bytes(2, "big") for r in rows)

    # 7f. Redrawn picture text (stage 03b): each block with an edited copy is packed again and
    # written over its original ("raw" blocks, stored unpacked, are written back as they are). The space
    # a smaller block leaves free is kept per bank; a block
    # that grew moves into such space in its own bank, and the address operands listed in its
    # "address_code" (LDX #address) are changed to the new place.
    if bmap.get("graphics"):
        gdir = os.path.normpath(os.path.join(os.path.dirname(map_path), bmap["graphics"]["dir"]))
        spare, grown = {}, []
        for g in json.load(open(os.path.join(gdir, "gfx-map.json"), encoding="utf-8")):
            path = os.path.join(gdir, "edited", g["id"] + ".bin")
            if not os.path.exists(path):
                continue
            off, fmt = num(g["offset"]), g["format"]
            if fmt == "raw":                # tiles stored unpacked: written back in place, same size
                data = open(path, "rb").read()
                if len(data) != g["unpacked"]:
                    errors.append(f"{g['id']}: raw block is {len(data)} bytes, not {g['unpacked']} (graphics)")
                    continue
                rom[off:off + len(data)] = data
                report.append(("gfx", off, len(data), g["id"]))
                continue
            packed = PACK[fmt](open(path, "rb").read())
            _, room = UNPACK[fmt](orig, off)
            if len(packed) > room:
                grown.append((g, off, packed))
                continue
            rom[off:off + len(packed)] = packed
            spare.setdefault(off >> 15, []).append([off + len(packed), off + room])
            report.append(("gfx", off, len(packed), g["id"]))
        for g, off, packed in grown:
            span = next((s for s in spare.get(off >> 15, []) if s[1] - s[0] >= len(packed)), None)
            if span is None or not g.get("address_code"):
                errors.append(f"{g['id']}: packed {len(packed)} bytes does not fit at {g['offset']} and no spare "
                              f"space in its bank{'' if g.get('address_code') else ' (and no address_code)'} (graphics)")
                continue
            new = span[0]
            span[0] += len(packed)
            for site in g["address_code"]:
                at = num(site["address_operand"])
                if int.from_bytes(orig[at:at + 2], "little") != 0x8000 + (off & 0x7FFF):
                    errors.append(f"{g['id']}: address operand {site['address_operand']} does not hold {g['snes']}")
                rom[at:at + 2] = (0x8000 + (new & 0x7FFF)).to_bytes(2, "little")
            rom[new:new + len(packed)] = packed
            report.append(("gfx", new, len(packed), g["id"] + " (moved)"))

    # 7g. Name parity: a line drawn right after a name (narrow, letter pairs) has two versions. After a name with
    # an even number of letters it starts with its space; after an odd one the name's last cell already ends in a
    # space, so the "en_odd" version (no space) is drawn. A parity table (one byte per name: 0 or 2 x the number of
    # lines) and a pointer table (the lines, then their odd versions) go into free space with a small routine that
    # picks the line; the code at "hook" (its "hook_old" bytes) becomes a JSL to it and NOPs. The routine takes the
    # line number from "line_var" and the name number from "name_var" (direct RAM, 8-bit), runs with a 16-bit
    # accumulator and returns the line's address in A, read with a long address (the data bank stays the line's).
    for spec in bmap.get("name_parity", []):
        job = next((j for j in name_jobs if spec["names_ref"] in j.get("refs", [])), None)
        lines = spec["lines"]
        if job is None or len(job["texts"]) != job["count"] or not all(i in B.new and i + "/odd" in B.odd for i in lines):
            errors.append(f"name parity {spec['hook']}: names or line versions missing")
            continue
        hook, old = num(spec["hook"]), bytes.fromhex(spec["hook_old"])
        if orig[hook:hook + len(old)] != old:
            errors.append(f"name parity: {spec['hook']} does not hold {spec['hook_old']}")
            continue
        parity = bytes(2 * len(lines) * (len(t) % 2) for t in job["texts"]) + b"\x00"
        table = b"".join(addr16(B.new[i]).to_bytes(2, "little") for i in lines)
        table += b"".join(addr16(B.odd[i + "/odd"]).to_bytes(2, "little") for i in lines)
        size = 32 + len(parity) + len(table)
        at = take(free[spec["bank"]], size)
        if at is None:
            errors.append(f"name parity: no room in bank {spec['bank']}")
            continue
        long = lambda off: addr16(off).to_bytes(2, "little") + bytes([0x80 | off >> 15])
        par_at, tab_at = at + 32, at + 32 + len(parity)
        nv, lv = num(spec["name_var"]).to_bytes(2, "little"), num(spec["line_var"]).to_bytes(2, "little")
        code = (b"\xAD" + nv + b"\x29\xFF\x00\xAA"             # LDA name / AND #$00FF / TAX
                + b"\xBF" + long(par_at) + b"\x29\xFF\x00\x48"   # LDA parity,X / AND #$00FF / PHA
                + b"\xAD" + lv + b"\x29\xFF\x00\x0A\x18"       # LDA line / AND #$00FF / ASL / CLC
                + b"\x63\x01\xAA\x68"                           # ADC 1,S / TAX / PLA
                + b"\xBF" + long(tab_at) + b"\x6B")               # LDA table,X / RTL
        assert len(code) == 32
        rom[at:at + size] = code + parity + table
        rom[hook:hook + len(old)] = b"\x22" + long(at) + b"\xEA" * (len(old) - 4)
        report.append(("parity", at, size, spec["hook"]))

    # 7h. Fleet message builder ($8B:D782, BUG-058): the game joins "[A] <piece> [B] <piece>" with a name in the
    # middle, where a name with an odd number of letters gets a double space. A new routine in free space builds the
    # three messages so that the second name ends the message and carries its "!" ("name_end" tables, see 4d):
    # contact "A vs B!", invasion "A storms P!", invaded "P invaded by B!". The code at "hook" ("hook_old") becomes
    # JSL to it and JMP to "back" (the end marker and the display call).
    fm = bmap.get("fleet_messages")
    if fm:
        jobs_by = {k: j for j in name_jobs for k in j.get("refs", []) + ([j["id"]] if j.get("id") else [])}
        need = [fm["names"][k] for k in ("officer", "planet", "officer_end", "planet_end")]
        hook, old = num(fm["hook"]), bytes.fromhex(fm["hook_old"])
        if not all(n in jobs_by and "new_at" in jobs_by[n] for n in need) or not all(i in B.new for i in fm["pieces"].values()):
            errors.append("fleet messages: a name table or a piece is missing")
        elif orig[hook:hook + len(old)] != old:
            errors.append(f"fleet messages: {fm['hook']} does not hold {fm['hook_old']}")
        else:
            long = lambda off: addr16(off).to_bytes(2, "little") + bytes([0x80 | off >> 15])
            tab = {k: long(jobs_by[n]["new_at"]) for k, n in fm["names"].items()}
            piece = {k: addr16(B.new[i]).to_bytes(2, "little") for k, i in fm["pieces"].items()}
            ofs, plan = {}, []                      # (bytes or (label, kind)) items; branches resolved below

            def asm(*items):
                plan.extend(items)
            name_b = [b"\xAD\x41\x09\x29\xFF\x00\x0A\xAA\xBF" + tab["officer_end"] + b"\xAA", ("copyL", "jsr")]
            asm(b"\x08\xC2\x30\xA0\x10\x0E",                         # PHP / REP #$30 / LDY #$0E10
                b"\xAD\x32\x09\x29\xFF\x00\xC9\xFF\x00", ("invaded", "beq"),
                b"\x0A\xAA\xBF" + tab["officer"] + b"\xAA", ("copy0", "jsr"),
                b"\xAD\x41\x09\x29\xFF\x00\xC9\xFF\x00", ("invasion", "beq"),
                b"\xA2" + piece["vs"], ("copy0", "jsr"), *name_b, ("done", "bra"),
                "invasion", b"\xA2" + piece["storms"], ("copy0", "jsr"),
                b"\xAD\x71\x09\x29\x7F\x00\x0A\xAA\xBF" + tab["planet_end"] + b"\xAA", ("copyL", "jsr"), ("done", "bra"),
                "invaded", b"\xAD\x71\x09\x29\x7F\x00\x0A\xAA\xBF" + tab["planet"] + b"\xAA", ("copy0", "jsr"),
                b"\xA2" + piece["invaded_by"], ("copy0", "jsr"), *name_b,
                "done", b"\x28\x6B")                                  # PLP / RTL
            for label, bank in (("copy0", 0x80), ("copyL", 0x80 | num(fm["bank"]) & 0x7F)):
                asm(label, b"\xBF\x00\x00" + bytes([bank]) + b"\xC9\xFF\xFF\xF0\x09\x99\x00\x00\xE8\xE8\xC8\xC8\x80\xEE\x60")
            size = sum(len(x) if isinstance(x, bytes) else (0 if isinstance(x, str) else 3 if x[1] == "jsr" else 2)
                       for x in plan)
            at = take(free[fm["bank"]], size)
            if at is None:
                errors.append(f"fleet messages: no room in bank {fm['bank']}")
            else:
                pos = 0
                for x in plan:
                    if isinstance(x, str):
                        ofs[x] = pos
                    else:
                        pos += len(x) if isinstance(x, bytes) else 3 if x[1] == "jsr" else 2
                code, pos = b"", 0
                for x in plan:
                    if isinstance(x, str):
                        continue
                    if isinstance(x, bytes):
                        code += x
                    elif x[1] == "jsr":
                        code += b"\x20" + addr16(at + ofs[x[0]]).to_bytes(2, "little")
                    else:
                        rel = ofs[x[0]] - (len(code) + 2)
                        if not -128 <= rel < 128:
                            errors.append(f"fleet messages: branch to {x[0]} out of range")
                        code += bytes([{"beq": 0xF0, "bra": 0x80}[x[1]], rel & 0xFF])
                rom[at:at + len(code)] = code
                back = num(fm["back"])
                rom[hook:hook + len(old)] = b"\x22" + long(at) + b"\x4C" + back.to_bytes(2, "little")
                report.append(("fleetmsg", at, len(code), fm["hook"]))

    if errors:
        print("\n".join(errors))
        sys.exit(f"{len(errors)} error(s); nothing written")

    # 7c. Narrow letter pairs into their glyph slots.
    for code, pair in glyphs.items():
        rom[FONT_BASE + 24 * code:FONT_BASE + 24 * (code + 1)] = pair_glyph(font, pair)
    for code, rows in prop_glyphs.items():
        rom[FONT_BASE + 24 * code:FONT_BASE + 24 * (code + 1)] = b"".join((r << 4).to_bytes(2, "big") for r in rows)

    # 8. Header checksum (LoROM header at 0x7FC0).
    rom[0x7FDC:0x7FE0] = b"\xFF\xFF\x00\x00"
    total = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FE0] = (total ^ 0xFFFF).to_bytes(2, "little") + total.to_bytes(2, "little")

    with open(out_path, "wb") as f:
        f.write(rom)
    for bank, start, size, name in sorted(report, key=lambda r: r[1]):
        print(f"bank {bank}  0x{start:06X}  {size:6d} bytes  {name}")
    left = {k: sum(b - a for a, b in v) for k, v in free.items()}
    print(f"placed {len(report)} unit(s), {len(B.new)} line(s); free left per bank: {left}")
    print(f"checksum {total:04X} -> {out_path}")


if __name__ == "__main__":
    main()
