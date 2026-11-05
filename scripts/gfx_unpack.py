"""Unpack the game's packed graphics and draw them as a tile sheet.

usage: gfx_unpack.py ROM FORMAT OFFSET OUTDIR [--bpp 4] [--cgram FILE --palette N] [--name NAME] [--size N]

FORMAT is "lz" (the game's unpacker at $00:8401), "rle" (the word unpacker at $BA:82B2) or "raw" (tiles
stored unpacked, copied to VRAM as they are; --size gives the byte count).
OFFSET is a file offset (0x168000). Writes OUTDIR/NAME.bin (the unpacked bytes) and OUTDIR/NAME.png
(8 x 8 tiles, 16 per row, drawn 2x). NAME defaults to the offset. Without --cgram the sheet is grey;
with a 512-byte palette dump (CGRAM, from Mesen) it uses palette N of that dump.

Formats (read from the game's code):
  lz:  2-byte size, then groups of a flag byte (bit 7 first) and 8 items. Flag 0: one literal byte.
       Flag 1: two bytes [256 - distance][length, 0 = 256]: copy from that far back in the output.
  rle: control bytes, 0 ends. count = c >> 2 (16-bit words), kind = c & 3: 0 = that many literal
       words follow, 2 = repeat the last word, 1 = last word + 1 each time, 3 = last word - 1.
"""
import os
import struct
import sys
import zlib


def unpack_lz(rom, off):
    """-> (unpacked bytes, packed size)."""
    size = int.from_bytes(rom[off:off + 2], "little")
    p, out = off + 2, bytearray()
    while len(out) < size:
        flags = rom[p]
        p += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                dist, n = 256 - rom[p], rom[p + 1] or 256
                p += 2
                for _ in range(n):
                    out.append(out[-dist])
            else:
                out.append(rom[p])
                p += 1
    return bytes(out), p - off


def unpack_rle(rom, off):
    """-> (unpacked bytes, packed size)."""
    p, out, prev = off, bytearray(), 0
    while True:
        c = rom[p]
        p += 1
        if c == 0:
            return bytes(out), p - off
        n, kind = c >> 2, c & 3
        for _ in range(n):
            if kind == 0:
                prev = int.from_bytes(rom[p:p + 2], "little")
                p += 2
            elif kind == 1:
                prev = (prev + 1) & 0xFFFF
            elif kind == 3:
                prev = (prev - 1) & 0xFFFF
            out += prev.to_bytes(2, "little")


UNPACK = {"lz": unpack_lz, "rle": unpack_rle}


def tile_pixels(data, bpp):
    """SNES planar tiles -> list of 8 x 8 lists of colour indexes."""
    size = 8 * bpp
    tiles = []
    for t in range(len(data) // size):
        b = data[size * t:size * (t + 1)]
        tiles.append([[sum(((b[(pl // 2) * 16 + 2 * y + (pl % 2)] >> (7 - x)) & 1) << pl for pl in range(bpp))
                       for x in range(8)] for y in range(8)])
    return tiles


def palette_rgb(cgram, index, bpp):
    """Colours of one palette from a CGRAM dump (BGR555), or a grey ramp."""
    count = 1 << bpp
    if cgram is None:
        return [(v * 255 // (count - 1),) * 3 for v in range(count)]
    words = [int.from_bytes(cgram[2 * i:2 * i + 2], "little") for i in range(index * count, (index + 1) * count)]
    return [((w & 31) * 255 // 31, (w >> 5 & 31) * 255 // 31, (w >> 10 & 31) * 255 // 31) for w in words]


def write_png(path, rows, scale=2):
    """rows: list of lists of (r, g, b)."""
    h, w = len(rows), len(rows[0])
    raw = b"".join((b"\x00" + b"".join(bytes(px) * scale for px in row)) * scale for row in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def sheet(data, bpp, colours, per_row=16):
    tiles = tile_pixels(data, bpp)
    rows = [[(64, 32, 32)] * (8 * per_row) for _ in range(8 * max(1, -(-len(tiles) // per_row)))]
    for t, px in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                rows[(t // per_row) * 8 + y][(t % per_row) * 8 + x] = colours[px[y][x]]
    return rows


def main():
    args = sys.argv[1:]
    opts = {}
    for key in ("--bpp", "--cgram", "--palette", "--name", "--size"):
        if key in args:
            i = args.index(key)
            opts[key] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 4 or args[1] not in UNPACK and not (args[1] == "raw" and "--size" in opts):
        sys.exit(__doc__)
    rom_path, fmt, off, outdir = args
    rom, off = open(rom_path, "rb").read(), int(off, 0)
    if fmt == "raw":
        data = rom[off:off + int(opts["--size"], 0)]
        used = len(data)
    else:
        data, used = UNPACK[fmt](rom, off)
    bpp = int(opts.get("--bpp", 4))
    cgram = open(opts["--cgram"], "rb").read() if "--cgram" in opts else None
    name = opts.get("--name", f"{off:06X}")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, name + ".bin"), "wb") as f:
        f.write(data)
    write_png(os.path.join(outdir, name + ".png"), sheet(data, bpp, palette_rgb(cgram, int(opts.get("--palette", 0)), bpp)))
    print(f"{fmt} 0x{off:06X}: {used} packed bytes -> {len(data)} bytes ({len(data) // (8 * bpp)} tiles at {bpp}bpp)"
          f" -> {os.path.join(outdir, name)}.bin/.png")


if __name__ == "__main__":
    main()
