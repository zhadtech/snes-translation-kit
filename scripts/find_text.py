"""Find text in a ROM.

--word KANA : relative search. Finds a 1-byte encoding where kana keep their order
              (a table in gojuon order). Works without knowing the table.
--sjis      : list runs of Shift-JIS text.
"""
import argparse


GOJUON = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"


def to_hira(c):
    """Katakana to hiragana, so one word works for both scripts."""
    return chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c


def deltas_for(word, order):
    """Step between neighbouring characters, in the chosen kana ordering."""
    if order == "unicode":
        return [ord(b) - ord(a) for a, b in zip(word, word[1:])]
    idx = [GOJUON.find(to_hira(c)) for c in word]
    if -1 in idx:
        return None  # word has a kana outside the plain 46 (dakuten, small kana, kanji)
    return [b - a for a, b in zip(idx, idx[1:])]


def relative_search(rom, word, context):
    if len(word) < 2:
        raise SystemExit("use a word with at least 2 characters")
    for order in ("gojuon", "unicode"):
        deltas = deltas_for(word, order)
        if deltas is None:
            print(f"[{order}] skipped: word has kana outside the plain 46")
            continue
        hits = 0
        for i in range(len(rom) - len(word) + 1):
            if all(rom[i + k + 1] - rom[i + k] == d for k, d in enumerate(deltas)):
                hits += 1
                snippet = rom[max(0, i - context):i + len(word) + context]
                print(f"[{order}] 0x{i:06X}  first byte 0x{rom[i]:02X} = {word[0]!r}  context: {snippet.hex(' ')}")
        print(f"[{order}] {hits} hit(s). Short words give false hits; check each against the game.")


def sjis_runs(rom, min_chars):
    i, hits = 0, 0
    while i < len(rom) - 1:
        j = i
        while j < len(rom) - 1:
            lead = rom[j]
            if (0x81 <= lead <= 0x9F or 0xE0 <= lead <= 0xEF) and 0x40 <= rom[j + 1] <= 0xFC:
                try:
                    bytes(rom[j:j + 2]).decode("shift_jis")
                    j += 2
                    continue
                except UnicodeDecodeError:
                    pass
            break
        if (j - i) // 2 >= min_chars:
            text = bytes(rom[i:j]).decode("shift_jis", "replace")
            print(f"0x{i:06X}  {text[:60]}")
            hits += 1
        i = max(j, i + 1)
    print(f"{hits} run(s) of {min_chars}+ characters.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("rom")
    p.add_argument("--word", help="known kana word, e.g. はい")
    p.add_argument("--sjis", action="store_true")
    p.add_argument("--min", type=int, default=6, help="min characters for --sjis runs")
    p.add_argument("--context", type=int, default=6, help="bytes of context to show")
    a = p.parse_args()
    rom = open(a.rom, "rb").read()
    if a.word:
        relative_search(rom, a.word, a.context)
    if a.sjis:
        sjis_runs(rom, a.min)
    if not a.word and not a.sjis:
        p.print_help()


if __name__ == "__main__":
    main()
