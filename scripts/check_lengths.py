"""Check that translated lines encode and fit their original space.

usage: check_lengths.py TBL TRANSLATED_DIR [--map BUILD_MAP]
Exit code 1 if any line fails.

With --map (stages/04_build/output/build-map.json), the sentence blocks listed in its "narrow_text"
are also checked for letter pairs (two narrow letters per cell, see scripts/narrow_text.py): rows per
box, words longer than a row, name tokens, pieces before a new line, script screen lines, code-joined
messages ("joined": names and pieces on one row), and letters the narrow font does not have. Blocks the
build sets in letter pairs now ("active") are size-checked as pairs. It also counts the letter pairs all
those blocks would need, against the glyph pool.
"""
import glob
import json
import os
import re
import sys

from narrow_text import (PIECE_LEAD, SCRIPT_LEAD, TOKEN, check_box_block, check_joined, check_script_block, even,
                         name_before, pairs_of, split_lead, wrap)
from tbl import encode, load_tbl


def load_narrow_letters(path):
    return {(" " if m.group(1) == "space" else m.group(1))
            for m in re.finditer(r"^(\S+) @\d+$", open(path, encoding="utf-8").read(), re.M)}


def main():
    args = sys.argv[1:]
    map_path = None
    if "--map" in args:
        k = args.index("--map")
        map_path = args[k + 1]
        del args[k:k + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    table = load_tbl(args[0])
    blocks = {}
    for path in sorted(glob.glob(os.path.join(args[1], "B*.json"))):
        bid = os.path.basename(path)[:-5]
        blocks[bid] = json.load(open(path, encoding="utf-8"))["lines"]

    ntext, letters, pool = {}, set(), 0
    if map_path:
        bmap = json.load(open(map_path, encoding="utf-8"))
        ntext = bmap.get("narrow_text", {})
        letters = load_narrow_letters(os.path.join(os.path.dirname(map_path), bmap["narrow"]["font"]))
        pool = len(bmap["narrow"]["slots"])
    boxes, script = ntext.get("box", {}), ntext.get("script", {})
    scripts = set(script.get("blocks", []))
    active = set(ntext.get("active", []))
    skip = set(script.get("skip", [])) | {i for c in boxes.values() for i in c.get("skip", [])}

    def pair_bytes(line):
        """Bytes of a line in letter pairs: its lead, 2 per cell, 2 per name token."""
        bid = line["id"].split("-")[0]
        box = boxes.get(bid)
        lead_re = SCRIPT_LEAD if bid in scripts else PIECE_LEAD if box and box.get("pieces") else ""
        lead, body = split_lead(line["en"], lead_re)
        if box:
            body, _, _ = wrap(body, dict(box, rows=None) if box.get("pieces") else box, line.get("src"),
                              line.get("plain"), name_before(box, line["id"]))
        return len(encode(lead, table)) + 2 * len(pairs_of(body)) + 2 * len(TOKEN.findall(body))

    bad = done = 0
    for bid, lines in blocks.items():
        for line in lines:
            if not line.get("en"):
                continue
            done += 1
            try:
                if bid in active and line["id"] not in skip:
                    size = pair_bytes(line)     # letter pairs: a line break in the text is a row break
                else:
                    size = len(encode(line["en"], table))
            except ValueError as e:
                bad += 1
                print(f"{line['id']}: ENCODE ERROR {e}")
                continue
            if size > line["max_bytes"] and not line.get("repoint"):
                bad += 1
                print(f"{line['id']}: {size} bytes > {line['max_bytes']} allowed")

    if map_path:
        problems, missing, pairs = [], {}, set()
        for bid in sorted(set(boxes) | scripts):
            lines = blocks.get(bid, [])
            if bid in boxes:
                problems += check_box_block(lines, boxes[bid], skip)
            if bid in scripts:
                problems += check_script_block(lines, script)
            for line in lines:
                if line["id"] in skip or not line.get("en"):
                    continue
                for ch in set(TOKEN.sub("", line["en"])) - letters - {"\n"}:
                    missing.setdefault(ch, set()).add(bid)
                box = boxes.get(bid)
                lead_re = SCRIPT_LEAD if bid in scripts else PIECE_LEAD if box and box.get("pieces") else ""
                _, body = split_lead(line["en"], lead_re)
                if box:
                    body, _, _ = wrap(body, dict(box, rows=None) if box.get("pieces") else box, line.get("src"),
                              line.get("plain"), name_before(box, line["id"]))
                pairs |= {p for p in pairs_of(body) if p != "  "}
        joined = ntext.get("joined")
        if joined:
            parts = {i for msg in joined["messages"] for p in msg if isinstance(p, list) or p not in joined["names"]
                     for i in (p if isinstance(p, list) else [p])}
            jlines = [ln for bid in sorted({i.split("-")[0] for i in parts}) for ln in blocks.get(bid, [])
                      if ln["id"] in parts]
            problems += check_joined(jlines, joined)
            for line in jlines:
                for ch in set(line.get("en") or "") - letters:
                    missing.setdefault(ch, set()).add(line["id"].split("-")[0])
                pairs |= {p for p in pairs_of(even(line.get("en") or "", flow=False)) if p != "  "}
        for lid, msg in problems:
            print(f"{lid}: {msg} (letter pairs)")
        for ch, bids in sorted(missing.items()):
            print(f"narrow font has no {ch!r} (used in {', '.join(sorted(bids))})")
        bad += len(problems) + len(missing)
        print(f"letter pairs: {len(pairs)} distinct in the {len(set(boxes) | scripts)} sentence blocks "
              f"({len(active)} active); glyph pool {pool} slots (labels and names use some of them too)")
    print(f"{done} translated line(s) checked, {bad} problem(s).")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
