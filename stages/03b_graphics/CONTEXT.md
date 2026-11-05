# Stage 03b — Graphics

**Job:** Find text that the game draws as a picture (tiles), draw it again in English, and hand the
new tiles to stage 04. Text drawn with the font is not done here (stages 02–03).

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `../01_recon/input/<ROM>` | The original ROM (read only) |
| 4 | `../05_playtest/output/bugs.md` | The "Picture text" table: what to redraw, with screenshots |
| 4 | `../04_build/output/latin-font.txt`, `narrow-font.txt` | The game's English letters, to draw labels with |
| 3 | `../../_config/rom-facts.md` | Graphics formats and known blocks |
| 3 | `../../_config/glossary.md` | Fixed terms |
| 3 | `../../_config/style-guide.md` | Wording |
| 3 | `../../_config/tools.md` | Mesen headless runs |

## Process
1. **Inventory.** For each picture-text bug, open its screen in Mesen (headless) and find where its
   tiles come from: log the unpack calls (`$00:8401` for lz, `$BA:82B2` for rle) or the DMA copies
   into VRAM, then match the VRAM tiles against `gfx_unpack.py` output. Give each packed block an ID
   (`G01`, `G02`, …) and write it to `output/gfx-map.json`: bug IDs, format, file offset, packed and
   unpacked size, bits per pixel, palette, screens, and the code that sets its address.
   Run `gfx_unpack.py` for each block and keep the result in `output/original/Gxx.bin` and `.png`.
   Some picture text is not packed: the game copies tiles stored as they are straight from the ROM to VRAM. Log
   the DMA sources into VRAM on that screen; a source address in the ROM (not in RAM) is such a block (format
   `raw`). A shape search can miss these tiles when they have an outline or a colour fade.
2. **English.** For each label, write the English in `output/gfx-text.md`: block, Japanese, English,
   room in pixels. Use glossary terms and the shortest clear wording. The English must fit the
   label's own tiles. If it cannot, say which tile map (screen layout) must change, and why.
3. **Draw.** Draw the English into a copy of the unpacked block: `output/edited/Gxx.bin` (same size
   and format as the original) and `Gxx.png`. List each block's labels in `gfx-map.json` and run
   `gfx_draw.py draw` (it finds labels drawn with the game's 12 x 12 font; others are placed by hand).
   Use the game's letters (12-px or narrow) and only the colours the label already uses. Leave every
   tile that has no Japanese unchanged.
4. **Check.** Run `gfx_pack.py` on each edited block (round trip) with `--rom` and `--offset`, and
   note whether it still fits. Make `output/compare/Gxx.png`: original above, edited below.

## Outputs
| File | Content |
|---|---|
| `output/gfx-map.json` | One entry per packed block (`Gxx`): bugs, format, offset, sizes, palette, screens, address code |
| `output/gfx-text.md` | English for each label, with its room |
| `output/original/Gxx.bin`, `.png` | Unpacked original blocks (reference) |
| `output/edited/Gxx.bin`, `.png` | New unpacked blocks for stage 04 |
| `output/compare/Gxx.png` | Original and edited sheets, one above the other |
| `output/gfx-fonts.txt` | Extra small letter sets for picture labels (tiny, small caps) |
| `output/graphics-notes.md` | How each block was found and drawn, and the Verify results |

## Verify
- [ ] Every picture-text bug is in `gfx-map.json`, or listed in `graphics-notes.md` as not done, with a reason.
- [ ] Each edited block has the same size as its original; only tiles with Japanese changed.
- [ ] `gfx_pack.py` round trip is OK for every edited block; blocks that no longer fit are listed.
- [ ] Every English label matches the glossary.
Write the results under `## Verify` in `output/graphics-notes.md`.

## Review gate
Show the user the `compare/` sheets and the `gfx-text.md` table. Wait for "go". Then stage 04 packs
the edited blocks into the ROM (moving any block that grew), and stage 05 checks the screens.
