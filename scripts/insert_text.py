"""Write translated lines into a copy of the ROM (in place, no repointing).

usage: insert_text.py ROM TBL TRANSLATED_DIR OUT_ROM
Each line is encoded, then the terminator, then padded with the terminator byte.
A fixed-slot block ("record_bytes") gets no terminator: each slot is filled with its "pad" word.
Lines with no `en` are left as they are. The original ROM is never changed.
"""
import glob
import json
import os
import sys

from tbl import encode, load_tbl


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    rom_path, tbl_path, tdir, out_path = sys.argv[1:]
    if os.path.abspath(rom_path) == os.path.abspath(out_path):
        sys.exit("refusing to overwrite the original ROM")
    rom = bytearray(open(rom_path, "rb").read())
    table = load_tbl(tbl_path)
    count = 0
    for path in sorted(glob.glob(os.path.join(tdir, "B*.json"))):
        block = json.load(open(path, encoding="utf-8"))
        fixed = "record_bytes" in block
        term = b"" if fixed else bytes.fromhex(block["terminator"])
        pad = bytes.fromhex(block["pad"]) if fixed else b""
        for line in block["lines"]:
            if not line.get("en"):
                continue
            data = encode(line["en"], table)
            if len(data) > line["max_bytes"]:
                sys.exit(f"{line['id']}: {len(data)} bytes > {line['max_bytes']}. Run check_lengths.py.")
            slot = line["max_bytes"] + len(term)
            if fixed:
                body = data + pad * ((slot - len(data)) // len(pad))
            else:
                body = data + term
                body += term[:1] * (slot - len(body))
            rom[line["offset"]:line["offset"] + slot] = body
            count += 1
    with open(out_path, "wb") as f:
        f.write(rom)
    print(f"inserted {count} line(s) -> {out_path}")


if __name__ == "__main__":
    main()
