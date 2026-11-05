"""Sentences in letter pairs (narrow text): the layout rules shared by build_rom.py and check_lengths.py.

Two narrow letters share one 12-px glyph cell, so a box row of N cells holds 2N letters. The map entry
"narrow_text" (stages/04_build/output/build-map.json) describes each sentence block:

  "active": blocks the build sets in letter pairs now (the others keep one letter per cell)
  "box": {block: {"cells", "rows", "from", ...}}   text boxes that wrap by themselves
      cells      box width in cells (a row holds 2 x cells letters)
      rows       rows per box, or "src" (no more rows than the Japanese line, at `cells` per row)
      from       0 = the English is plain text; N = it was written for one letter per cell in rows of N
                 (padded with spaces), so the old rows are joined again before wrapping. A line marked
                 "plain": true in its translated file is plain text whatever `from` says (rewritten lines)
      keep_rows  the old rows are kept as rows (B11: army and leader, then the description)
      pieces     each line starts with a command (0 = new box, 1 = new line) and wraps on its own;
                 a box is a 0 line and the 1 lines after it (the block's first line has no command)
      piece_end  a piece followed by a 1 line must end its last row by this many cells
      indent     rows after the first start this many cells in (B20: under the text after the name)
      tokens     {token: letters}: a name the game inserts (<FFFD> planet, <FFFE> officer). It must start
                 the box's last row, and the rest of that row must fit beside the longest name
      skip       line ids that stay in one letter per cell (notices, pieces joined by code)
      label_lines  line ids (also in skip) joined with names and numbers by code: set in letter pairs as they
                 are, with no wrap; each should have an even number of letters (B12: the level-up pieces)
      name_before {"letters", "lines"}: the game draws a name (in letter pairs, ending on a whole cell)
                 before each listed line. Its width varies and the box wraps by count, so the line must
                 fit on the first row beside the longest name; a leading space is kept (B06: notices). A line
                 field "en_odd" is the version drawn after a name with an odd number of letters (no space)
  "script": {"blocks", "cells", "scene_starts", "same_line", "skip"}   cutscene scripts: each piece
      starts with its command (0, 1, 2n, 3ab, 5, 6); a screen line holds `cells` cells, the speaker
      name and the indent included. A 0 inside an open 「 (or a line in same_line) stays on its line.
  "joined": {"letters", "names", "messages"}   one-row messages that code joins from names and pieces
      (the message bar). Each piece fills whole cells; a message is a list of name kinds (letters at the
      longest, from "names") and line ids (a list = one of them, the longest counts). The visible letters
      must fit in "letters".

In plain text, a line break ("\\n" in the JSON string) starts a new row.
"""
import math
import re

TOKEN = re.compile(r"<[0-9A-F]{4}>")
PIECE_LEAD = r"(?:0|1)?"
SCRIPT_LEAD = r"(?:0|1|2\d|3\d\d|5|6)?"


def even(text, flow=True):
    """A piece fills whole cells: an odd letter count drops a trailing space, or gets one."""
    if len(text) % 2:
        return text[:-1] if flow and text.endswith(" ") else text + " "
    return text


def cells_of(text):
    """Cells a piece of letters takes in letter pairs (tokens count as 2 letters here: use wrap for names)."""
    return len(even(text)) // 2


def split_lead(text, lead_re):
    m = re.match(f"({lead_re})(.*)", text, re.S)
    return m.group(1), m.group(2)


def source_rows(src, cells):
    """Rows the Japanese line takes at `cells` per row (one glyph per cell; tokens and codes count 1)."""
    n = len(re.sub(r"<[0-9A-F]{4}>|\{[0-9A-F]{4}\}", "#", src))
    return max(1, math.ceil(n / cells))


def name_before(box, line_id):
    """Letters of the name the game draws before this line (0: none)."""
    nb = box.get("name_before")
    return nb["letters"] if nb and line_id in nb["lines"] else 0


def wrap(text, box, src=None, plain=False, name=0):
    """Lay out one box text (or one piece) in letter pairs. -> (laid-out text, rows used, errors).
    Full rows are padded with spaces to 2 x cells letters, so the box's own wrap falls between rows.
    `name`: letters of a name drawn before the text (see name_before); the text stays on that row."""
    W, errors = 2 * box["cells"], []
    old = 0 if plain else box.get("from") or 0
    if old:
        rows = [text[i:i + old].strip() for i in range(0, len(text), old)]
        text = ("\n" if box.get("keep_rows") else " ").join(r for r in rows if r)
    if name:
        laid = (" " if text.startswith(" ") else "") + " ".join(text.split())
        if name + len(even(laid)) > W:
            errors.append(f"{len(laid)} letters after a name of up to {name}: the first row holds {W}")
        return laid, 1, errors
    tok_w = box.get("tokens", {})
    unknown = sorted({t for t in TOKEN.findall(text) if t not in tok_w})
    if unknown:
        errors.append(f"token {unknown} has no width in the map")

    def vis(s):                             # letters on screen, a name counted at its longest
        return len(TOKEN.sub("", s)) + sum(tok_w.get(t, 12) for t in TOKEN.findall(s))

    indent = " " * (2 * box.get("indent", 0))
    rows, token_row = [""], None
    for para_no, para in enumerate(text.split("\n")):
        if para_no:
            rows.append("")
        for word in para.split():
            if TOKEN.search(word):
                if rows[-1].strip():
                    rows.append("")
                token_row = len(rows) - 1
            elif rows[-1].strip() and vis(rows[-1]) + 1 + vis(word) > W:
                rows.append("")
            if not rows[-1] and len(rows) > 1:
                rows[-1] = indent
            rows[-1] += (" " if rows[-1].strip() else "") + word
            room = W - (len(indent) if len(rows) > 1 else 0)
            if vis(word) > room:
                errors.append(f"word {word!r} is {vis(word)} letters, a row holds {room}")
    if token_row is not None:
        if token_row != len(rows) - 1:
            errors.append("a name token must start the last row")
        if vis(rows[token_row]) > W:
            errors.append(f"the name row needs {vis(rows[token_row])} letters with the longest name, a row holds {W}")
    limit = source_rows(src, box["cells"]) if box.get("rows") == "src" and src is not None else box.get("rows")
    if limit and len(rows) > limit:
        errors.append(f"{len(rows)} rows > {limit}")
    for r in rows:
        if TOKEN.search(r) is None and len(r) > W:
            errors.append(f"row {r!r} is {len(r)} letters > {W}")
    laid = "".join(r.ljust(W) for r in rows[:-1]) + rows[-1]
    return laid, len(rows), errors


def box_messages(lines):
    """Piece blocks: group line dicts into boxes (a 0 line and the 1 lines after it)."""
    boxes = []
    for k, ln in enumerate(lines):
        text = ln.get("en") or ""
        if k == 0 or text.startswith("0"):
            boxes.append([ln])
        else:
            boxes[-1].append(ln)
    return boxes


def check_box_block(lines, box, skip=()):
    """-> list of (line id, problem) for one box block."""
    out = []
    if not box.get("pieces"):
        for ln in lines:
            if ln["id"] in skip or not ln.get("en"):
                continue
            _, _, errs = wrap(ln["en"], box, ln.get("src"), ln.get("plain"), name_before(box, ln["id"]))
            out += [(ln["id"], e) for e in errs]
            if ln.get("en_odd"):        # the version drawn after a name with an odd number of letters
                _, _, errs = wrap(ln["en_odd"], box, ln.get("src"), True, name_before(box, ln["id"]))
                out += [(ln["id"] + "/odd", e) for e in errs]
        return out
    for msg in box_messages(lines):
        total = 0
        for k, ln in enumerate(msg):
            if ln["id"] in skip:
                continue
            lead, body = split_lead(ln.get("en") or "", PIECE_LEAD)
            laid, nrows, errs = wrap(body, dict(box, rows=None), plain=ln.get("plain"))
            out += [(ln["id"], e) for e in errs]
            total += nrows
            last_cells = cells_of(laid[2 * box["cells"] * (nrows - 1):])
            if box.get("piece_end") and k + 1 < len(msg) and last_cells > box["piece_end"]:
                out.append((ln["id"], f"ends its row at {last_cells} cells before a new line (max {box['piece_end']})"))
        if total > box["rows"]:
            out.append((msg[0]["id"], f"box needs {total} rows > {box['rows']}"))
    return out


def check_joined(lines, joined):
    """-> list of (first line id, problem) for the code-joined messages ("joined" in the map)."""
    by_id, out = {ln["id"]: ln for ln in lines}, []
    for msg in joined["messages"]:
        total, first = 0, None
        for k, part in enumerate(msg):
            if isinstance(part, str) and part in joined["names"]:
                total += joined["names"][part]
                continue
            ids = part if isinstance(part, list) else [part]
            missing = [i for i in ids if not (by_id.get(i) or {}).get("en")]
            if missing:
                out.append((ids[0], f"joined message: no English for {', '.join(missing)}"))
                continue
            first = first or ids[0]
            last = k == len(msg) - 1            # blanks at the very end are not seen
            total += max(len(by_id[i]["en"].rstrip() if last else even(by_id[i]["en"], flow=False)) for i in ids)
        if total > joined["letters"]:
            out.append((first, f"joined message {' + '.join(p if isinstance(p, str) else '/'.join(p) for p in msg)}"
                               f" needs {total} letters > {joined['letters']}"))
    return out


def script_lines(lines, script):
    """Screen lines of a script block in cells: -> list of (first id, last id, cells)."""
    starts, same = set(script.get("scene_starts", [])), set(script.get("same_line", []))
    skip = set(script.get("skip", []))
    out, cur, ids, open_q, first = [], 0, [], 0, True

    def flush():
        nonlocal cur, ids, open_q
        if ids and cur:
            out.append((ids[0], ids[-1], cur))
        cur, ids, open_q = 0, [], 0

    for ln in lines:
        text = ln.get("en") or ""
        start = ln["id"] in starts
        if start and not first and text.startswith("0"):
            text = text[1:]
        cmd, body = ("", text) if first or start else split_lead(text, SCRIPT_LEAD)
        if start and not first:
            flush()
        first = False
        n = 0 if ln["id"] in skip else cells_of(body)
        if cmd in ("0", "1") and not (cmd == "0" and (open_q > 0 or ln["id"] in same)):
            flush()
            cur = n
        elif cmd.startswith("2"):
            cur = max(cur, int(cmd[1])) + n
        else:
            cur += n
        open_q += body.count("「") - body.count("」")
        ids.append(ln["id"])
    flush()
    return out


def check_script_block(lines, script):
    return [(a, f"screen line {a}..{z} is {n} cells > {script['cells']}")
            for a, z, n in script_lines(lines, script) if n > script["cells"]]


def pairs_of(text):
    """Letter pairs of a laid-out text (tokens split it; each part fills whole cells)."""
    out = []
    for part in TOKEN.split(text):
        part = even(part)
        out += [part[i:i + 2] for i in range(0, len(part), 2)]
    return out
