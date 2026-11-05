# Table and block formats

## charset.tbl
One entry per line: `HEX=text`. Lines starting with `#` are comments.
```
# kana
80=あ
81=い
# control codes
F0=<WAIT>
F1=<NAME>
# two-byte entry
FE01=<PORTRAIT1>
```
Longest match wins. `<XX>` in a string stands for the raw byte XX.

## blocks.json
A list. Offsets are file offsets, not SNES addresses. Subtract any copier header (512 bytes) first.
```
[{"id": "B01", "start": "0x1A000", "end": "0x1B000", "terminator": "00", "note": "intro dialog"}]
```
`end` is exclusive. `terminator` is one byte that ends each line.
Limit: a line is split at every terminator byte, so a multi-byte code that contains the terminator breaks the split. If that happens, change the terminator or split the block by hand.

## script/Bxx.json
```
{"block": "B01", "terminator": "00",
 "lines": [{"id": "B01-001", "offset": 106496, "max_bytes": 14, "src": "…", "en": ""}]}
```
`max_bytes` = bytes in the original line, not counting the terminator. A translation must fit unless repointing is added in stage 04.
