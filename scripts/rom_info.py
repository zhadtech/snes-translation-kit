"""Print basic facts about a SNES ROM: header, map mode, size, checksums."""
import sys
import zlib

MAP_MODES = {0x20: "LoROM", 0x21: "HiROM", 0x30: "LoROM FastROM", 0x31: "HiROM FastROM",
             0x32: "ExLoROM", 0x35: "ExHiROM"}


def score(rom, base):
    """How much does the header at `base` look real? Higher is better."""
    if base + 0x30 > len(rom):
        return -1
    h = rom[base:base + 0x30]
    s = 0
    checksum = h[0x1E] | h[0x1F] << 8
    complement = h[0x1C] | h[0x1D] << 8
    if checksum ^ complement == 0xFFFF:
        s += 4
    if h[0x15] in MAP_MODES:
        s += 2
    if 0x08 <= h[0x17] <= 0x0D:
        s += 1
    if all(0x20 <= b < 0x7F or b >= 0xA0 for b in h[:21]):
        s += 1
    return s


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: rom_info.py ROM")
    raw = open(sys.argv[1], "rb").read()
    header = len(raw) % 1024 if len(raw) % 1024 in (0, 512) else 0
    rom = raw[header:]
    lo, hi = score(rom, 0x7FC0), score(rom, 0xFFC0)
    base = 0xFFC0 if hi > lo else 0x7FC0
    h = rom[base:base + 0x30]
    title = h[:21].decode("ascii", "replace")
    print(f"file size        : {len(raw)} bytes")
    print(f"copier header    : {header} bytes{' (remove it before patching)' if header else ''}")
    print(f"ROM size (no hdr): {len(rom)} bytes ({len(rom) // 1024} KB)")
    print(f"header guess     : {'HiROM' if base == 0xFFC0 else 'LoROM'} at 0x{base:X} (scores lo={lo}, hi={hi})")
    print(f"map mode byte    : 0x{h[0x15]:02X} ({MAP_MODES.get(h[0x15], 'unknown')})")
    print(f"internal title   : {title!r}")
    print(f"declared checksum: 0x{h[0x1E] | h[0x1F] << 8:04X}")
    print(f"CRC32 (no header): {zlib.crc32(rom) & 0xFFFFFFFF:08X}")
    print(f"CRC32 (as file)  : {zlib.crc32(raw) & 0xFFFFFFFF:08X}")
    print("note: file offsets in other scripts include any copier header.")


if __name__ == "__main__":
    main()
