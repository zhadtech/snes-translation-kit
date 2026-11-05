# Stage 02 — Extract

**Job:** Build the character table and dump all text into numbered JSON blocks.

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `../01_recon/input/<ROM>` | The original ROM |
| 4 | `../01_recon/output/rom-report.md` | Text offsets and encoding |
| 3 | `../../_config/rom-facts.md` | Facts to update |
| 3 | `references/table-format.md` | `.tbl` and `blocks.json` formats |

## Process
1. Build `output/charset.tbl` from the report (one `HEX=char` per line; control codes as `HEX=<NAME>`).
2. Write `output/blocks.json`: one entry per text region, with ID, start, end, terminator.
2b. Look for text that is not a string with an end mark. The string scans miss it (the first run found 9 such
   blocks late, in stages 04 and 05):
   - **Fixed-size slots:** runs of glyph codes padded with spaces and no terminator (menus, labels, army names,
     prompts), and records with a fixed size. Dump them with `record_bytes`, or `slots` when the sizes differ.
   - **Text written by code:** runs of `LDA/LDX/LDY #code` followed by a store, where the codes read as text, and
     code that writes a number between glyphs. Dump them with `operands`.
   - **Text inside scripts and demos:** the title screen's idle demo and similar scenes, whose line lengths may sit
     in the code.
3. Run `dump_text.py`. Fix the table until the Japanese reads correctly. Unmapped bytes show as `<XX>`.
4. Find pointers and control codes. Record them in `output/pointers.json` and `rom-facts.md`.
5. Measure the display limits (characters per line, lines per box) from the game, in Mesen, not from the space
   padding. For each box, also note any name or number the game's code draws before or inside its lines, with its
   widest width. Write them to `../03_translate/references/line-limits.md`.
6. Make a font-read log in Mesen over every screen you can reach, the title screen's idle demo included (wait on
   the title screen). Save which font glyphs are read in `output/dump-notes.md`. Stage 04 may reuse a glyph for new
   letters only if no dumped text uses it and the log never reads it.

## Outputs
| File | Content |
|---|---|
| `output/charset.tbl` | Character table |
| `output/blocks.json` | Block list |
| `output/script/Bxx.json` | Dumped lines with IDs `Bxx-nnn` |
| `output/pointers.json` | Pointer tables (may be empty) |
| `../03_translate/references/line-limits.md` | Display limits |

## Verify
- [ ] A random sample of 10 lines reads as real Japanese.
- [ ] Re-encoding every dumped line gives the original bytes (round-trip).
- [ ] Count of `<XX>` unmapped bytes is reported per block.
- [ ] The scans of step 2b were run, and their results are listed (blocks found, or none).
- [ ] Every box size in `line-limits.md` was measured in game, and names drawn by code are listed with their width.
- [ ] The font-read log covers every reachable screen and the idle demo; the list of read glyphs is saved.
Write the results under `## Verify` in `output/dump-notes.md`.

## Review gate
Tell the user to check the 20 sample lines in `dump-notes.md` against the game. Wait for "go".
