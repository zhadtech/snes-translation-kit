"""Character table helpers: load a .tbl file, decode bytes to text, encode text to bytes."""
import re


def load_tbl(path):
    """Return {bytes: text}. Lines look like HEX=text. '#' starts a comment line."""
    table = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            hex_part, sep, text = line.partition("=")
            if not sep or not text:
                raise ValueError(f"{path}:{n}: expected HEX=text")
            table[bytes.fromhex(hex_part.strip())] = text
    return table


def decode(data, table):
    """Bytes to text. Longest table match wins. Unmapped bytes become <XX>."""
    longest = max((len(k) for k in table), default=1)
    out, i = [], 0
    while i < len(data):
        for size in range(min(longest, len(data) - i), 0, -1):
            key = bytes(data[i:i + size])
            if key in table:
                out.append(table[key])
                i += size
                break
        else:
            out.append(f"<{data[i]:02X}>")
            i += 1
    return "".join(out)


def encode(text, table):
    """Text to bytes. Longest text match wins. <XX> is a raw byte."""
    reverse = {}
    for key, val in table.items():
        reverse.setdefault(val, key)
    longest = max((len(v) for v in reverse), default=1)
    out, i = bytearray(), 0
    while i < len(text):
        m = re.match(r"<([0-9A-Fa-f]{2})>", text[i:])
        if m and m.group(0) not in reverse:
            out.append(int(m.group(1), 16))
            i += 4
            continue
        for size in range(min(longest, len(text) - i), 0, -1):
            chunk = text[i:i + size]
            if chunk in reverse:
                out += reverse[chunk]
                i += size
                break
        else:
            raise ValueError(f"cannot encode {text[i]!r} at position {i} in {text!r}")
    return bytes(out)
