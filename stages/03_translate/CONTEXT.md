# Stage 03 — Translate

**Job:** Translate each dumped line into English that fits the limits.

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `../02_extract/output/script/Bxx.json` | Lines to translate (one block at a time) |
| 4 | `../02_extract/output/charset.tbl` | Which English characters the game can show |
| 3 | `../../_config/glossary.md` | Fixed names |
| 3 | `../../_config/style-guide.md` | Tone and format |
| 3 | `references/line-limits.md` | Characters per line, lines per box; letters per row for letter pairs |

## Process
1. Work one block at a time. Note the block in `PROGRESS.md`.
2. Fill `en` for every line. Keep control codes as they are. Keep the same line count.
   Before a block, read its rows in `references/line-limits.md`: a name or number that the game's code draws before
   or inside a line takes its widest width out of the room, and the English must read well next to it.
3. Add new names to `glossary.md` (main agent only).
4. Run `check_lengths.py` with `--map ../04_build/output/build-map.json` (it also checks the letter-pair
   limits of the sentence blocks, see `references/line-limits.md`). Shorten any line that is too long. Do not drop meaning.
5. Parallel work is safe by block: each sub-agent writes only its own `translated/Bxx.json`. The main agent edits the glossary.

## Outputs
| File | Content |
|---|---|
| `output/translated/Bxx.json` | Same structure as the source, with `en` filled |
| `../../_config/glossary.md` | New terms |

## Verify
- [ ] Every line has `en`, or is marked `"skip": true` with a reason.
- [ ] `check_lengths.py` reports no overflow.
- [ ] Every name matches the glossary.
- [ ] Control codes match the source line.
- [ ] Lines with a name or number drawn by code were checked at the longest name (in `check_lengths.py` or by hand).
Write the results under `## Verify` in `output/translation-notes.md`.

## Review gate
No required gate. The user may read `translated/` and edit `en` fields. Say which blocks are done. Wait for "go".
