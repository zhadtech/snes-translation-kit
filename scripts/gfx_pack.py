"""Pack graphics for the game's unpackers, and check that they unpack to the same bytes.

usage: gfx_pack.py FORMAT IN.bin OUT.bin [--rom ROM --offset OFFSET]

FORMAT is "lz" ($00:8401) or "rle" ($BA:82B2); see gfx_unpack.py for both formats.
Packs IN.bin, unpacks the result again and stops if it differs. With --rom and --offset it also
prints the size of the original packed block there, so you can see whether the new one still fits
(a bigger block must move to free space in stage 04, and its pointer must be changed).
"""
import sys

from gfx_unpack import UNPACK

WINDOW, LONGEST = 256, 256        # lz: distance 1-256, length 1-256


def _match(data, i):
    """Longest earlier copy for data[i:] -> (distance, length)."""
    best, room = (0, 0), min(LONGEST, len(data) - i)
    for dist in range(1, min(WINDOW, i) + 1):
        if data[i - dist] != data[i]:
            continue
        n = 1
        while n < room and data[i - dist + n] == data[i + n]:
            n += 1
        if n > best[1]:
            best = (dist, n)
            if n == room:
                break
    return best


def pack_lz(data):
    items, i = [], 0
    while i < len(data):
        dist, n = _match(data, i)
        if n >= 3 and i + 1 < len(data) and _match(data, i + 1)[1] > n + 1:
            n = 0                            # a longer copy starts one byte later: take a literal
        if n >= 3:
            items.append((dist, n))
            i += n
        else:
            items.append(data[i])
            i += 1
    out = bytearray(len(data).to_bytes(2, "little"))
    for g in range(0, len(items), 8):
        flags, body = 0, bytearray()
        for k, item in enumerate(items[g:g + 8]):
            if isinstance(item, tuple):
                flags |= 0x80 >> k
                body += bytes([(256 - item[0]) & 0xFF, item[1] & 0xFF])
            else:
                body.append(item)
        out += bytes([flags]) + body
    return bytes(out)


def pack_rle(data):
    if len(data) % 2:
        raise ValueError("rle data must be whole 16-bit words")
    words = [int.from_bytes(data[k:k + 2], "little") for k in range(0, len(data), 2)]
    n = len(words)
    best, step = [0] * (n + 1), [None] * (n + 1)      # cheapest bytes for words[i:], and how
    for i in range(n - 1, -1, -1):
        options = [(1 + 2 * k + best[i + k], (0, k)) for k in range(1, min(63, n - i) + 1)]
        if i:                                           # the first word has no "last word" yet
            for kind, delta in ((2, 0), (1, 1), (3, -1)):
                m = 0
                while m < 63 and i + m < n and words[i + m] == (words[i - 1] + delta * (m + 1)) & 0xFFFF:
                    m += 1
                options += [(1 + best[i + r], (kind, r)) for r in range(1, m + 1)]
        best[i], step[i] = min(options)
    out, i = bytearray(), 0
    while i < n:
        kind, count = step[i]
        out.append(count << 2 | kind)
        if kind == 0:
            out += b"".join(w.to_bytes(2, "little") for w in words[i:i + count])
        i += count
    return bytes(out + b"\x00")


PACK = {"lz": pack_lz, "rle": pack_rle}


def main():
    args = sys.argv[1:]
    opts = {}
    for key in ("--rom", "--offset"):
        if key in args:
            i = args.index(key)
            opts[key] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 3 or args[0] not in PACK:
        sys.exit(__doc__)
    fmt, src, dst = args
    data = open(src, "rb").read()
    packed = PACK[fmt](data)
    again, used = UNPACK[fmt](packed, 0)
    if again != data or used != len(packed):
        sys.exit(f"round trip failed: {fmt} packing of {src} does not unpack to the same bytes")
    with open(dst, "wb") as f:
        f.write(packed)
    line = f"{fmt}: {len(data)} bytes -> {len(packed)} packed -> {dst} (round trip OK)"
    if "--rom" in opts:
        rom = open(opts["--rom"], "rb").read()
        _, old = UNPACK[fmt](rom, int(opts["--offset"], 0))
        line += f"; original block {old} bytes ({'fits' if len(packed) <= old else f'{len(packed) - old} bytes too big'})"
    print(line)


if __name__ == "__main__":
    main()
