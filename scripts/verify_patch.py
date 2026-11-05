"""Apply a BPS patch to the original ROM and compare with the patched ROM.

usage: verify_patch.py ORIGINAL PATCH.bps PATCHED
Exit code 0 only if the result is byte-identical and all checksums match.
Reads any BPS patch, so it also checks patches from other tools.
"""
import struct
import sys
import zlib


def read_varint(buf, pos):
    data, shift = 0, 1
    while True:
        x = buf[pos]
        pos += 1
        data += (x & 0x7F) * shift
        if x & 0x80:
            return data, pos
        shift <<= 7
        data += shift


def apply_bps(src, patch):
    if patch[:4] != b"BPS1":
        raise ValueError("not a BPS patch")
    if zlib.crc32(patch[:-4]) & 0xFFFFFFFF != struct.unpack("<I", patch[-4:])[0]:
        raise ValueError("patch checksum mismatch (patch is damaged)")
    src_crc, tgt_crc = struct.unpack("<II", patch[-12:-4])
    if zlib.crc32(src) & 0xFFFFFFFF != src_crc:
        raise ValueError("source ROM does not match the patch (wrong ROM or header?)")
    pos = 4
    src_size, pos = read_varint(patch, pos)
    tgt_size, pos = read_varint(patch, pos)
    meta, pos = read_varint(patch, pos)
    pos += meta
    out = bytearray()
    src_rel = tgt_rel = 0
    end = len(patch) - 12
    while pos < end:
        v, pos = read_varint(patch, pos)
        mode, length = v & 3, (v >> 2) + 1
        if mode == 0:
            out += src[len(out):len(out) + length]
        elif mode == 1:
            out += patch[pos:pos + length]
            pos += length
        else:
            off, pos = read_varint(patch, pos)
            off = -(off >> 1) if off & 1 else off >> 1
            if mode == 2:
                src_rel += off
                out += src[src_rel:src_rel + length]
                src_rel += length
            else:
                tgt_rel += off
                for _ in range(length):
                    out.append(out[tgt_rel])
                    tgt_rel += 1
    if len(out) != tgt_size or zlib.crc32(out) & 0xFFFFFFFF != tgt_crc:
        raise ValueError("result does not match the target checksum")
    return bytes(out)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src = open(sys.argv[1], "rb").read()
    patch = open(sys.argv[2], "rb").read()
    want = open(sys.argv[3], "rb").read()
    got = apply_bps(src, patch)
    if got != want:
        sys.exit("FAIL: patch applies but the result differs from the patched ROM")
    print(f"OK: patch applies cleanly. result CRC32 {zlib.crc32(got) & 0xFFFFFFFF:08X}")


if __name__ == "__main__":
    main()
