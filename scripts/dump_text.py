"""Dump text blocks from a ROM to JSON files, one per block.

usage: dump_text.py ROM TBL BLOCKS_JSON OUTDIR
A block with "record_bytes" is a run of fixed-size slots with no terminator: each slot is one line.
A block with "operands" is text written by code one glyph at a time: each entry is a list of file
offsets of 2-byte instruction operands (one glyph code each), read in order as one line.
A block with "slots" is a run of slots of different sizes with no terminator: each number is one line's
length in glyph cells (2 bytes each), read in order from "start".
"""
import json
import os
import sys

from tbl import decode, load_tbl


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    rom_path, tbl_path, blocks_path, outdir = sys.argv[1:]
    rom = open(rom_path, "rb").read()
    table = load_tbl(tbl_path)
    os.makedirs(outdir, exist_ok=True)
    for block in json.load(open(blocks_path)):
        start, end = int(block["start"], 0), int(block["end"], 0)
        lines, pos, n = [], start, 1
        if "operands" in block:
            for ops in block["operands"]:
                raw = b"".join(rom[int(a, 0):int(a, 0) + 2] for a in ops)
                lines.append({"id": f"{block['id']}-{n:03d}", "offset": int(ops[0], 0), "max_bytes": len(raw),
                              "operands": ops, "src": decode(raw, table), "en": ""})
                n += 1
            out = {"block": block["id"], "terminator": block["terminator"], "lines": lines}
        elif "slots" in block:
            for cells in block["slots"]:
                lines.append({"id": f"{block['id']}-{n:03d}", "offset": pos,
                              "max_bytes": 2 * cells, "src": decode(rom[pos:pos + 2 * cells], table), "en": ""})
                pos, n = pos + 2 * cells, n + 1
            out = {"block": block["id"], "terminator": block["terminator"], "pad": block["pad"], "lines": lines}
        elif "record_bytes" in block:
            size = block["record_bytes"]
            for pos in range(start, end, size):
                lines.append({"id": f"{block['id']}-{n:03d}", "offset": pos,
                              "max_bytes": size, "src": decode(rom[pos:pos + size], table), "en": ""})
                n += 1
            out = {"block": block["id"], "terminator": block["terminator"],
                   "record_bytes": size, "pad": block["pad"], "lines": lines}
        else:
            term = bytes.fromhex(block["terminator"])
            while pos < end:
                stop = rom.find(term, pos, end)
                if stop == -1:
                    stop = end
                raw = rom[pos:stop]
                if raw:
                    lines.append({"id": f"{block['id']}-{n:03d}", "offset": pos,
                                  "max_bytes": len(raw), "src": decode(raw, table), "en": ""})
                    n += 1
                pos = stop + len(term)
            out = {"block": block["id"], "terminator": block["terminator"], "lines": lines}
        path = os.path.join(outdir, f"{block['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        unmapped = sum(l["src"].count("<") for l in lines)
        print(f"{block['id']}: {len(lines)} lines, ~{unmapped} '<' marks (unmapped or control) -> {path}")


if __name__ == "__main__":
    main()
