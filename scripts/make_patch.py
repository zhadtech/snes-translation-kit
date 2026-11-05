"""Make a BPS patch (simple, correct, not size-optimal).

usage: make_patch.py ORIGINAL PATCHED OUT.bps
"""
import struct
import sys
import zlib


def varint(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def make_bps(src, tgt):
    patch = bytearray(b"BPS1")
    patch += varint(len(src)) + varint(len(tgt)) + varint(0)
    i, n = 0, len(tgt)
    while i < n:
        same = i < len(src) and src[i] == tgt[i]
        j = i
        if same:
            while j < n and j < len(src) and src[j] == tgt[j]:
                j += 1
            patch += varint(((j - i) - 1) << 2 | 0)  # SourceRead
        else:
            while j < n and not (j < len(src) and src[j] == tgt[j]):
                j += 1
            patch += varint(((j - i) - 1) << 2 | 1) + tgt[i:j]  # TargetRead
        i = j
    patch += struct.pack("<I", zlib.crc32(src) & 0xFFFFFFFF)
    patch += struct.pack("<I", zlib.crc32(tgt) & 0xFFFFFFFF)
    patch += struct.pack("<I", zlib.crc32(bytes(patch)) & 0xFFFFFFFF)
    return bytes(patch)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, tgt = open(sys.argv[1], "rb").read(), open(sys.argv[2], "rb").read()
    patch = make_bps(src, tgt)
    open(sys.argv[3], "wb").write(patch)
    print(f"patch: {len(patch)} bytes | source CRC32 {zlib.crc32(src) & 0xFFFFFFFF:08X} "
          f"| target CRC32 {zlib.crc32(tgt) & 0xFFFFFFFF:08X}")


if __name__ == "__main__":
    main()
