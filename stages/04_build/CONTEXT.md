# Stage 04 — Build

**Job:** Insert the English text, fix the font if needed, and produce the patched ROM, the BPS patch, and the instructions.

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `../01_recon/input/<ROM>` | The original ROM (read only) |
| 4 | `../03_translate/output/translated/Bxx.json` | English text |
| 4 | `../02_extract/output/charset.tbl` | Encoding |
| 4 | `../03b_graphics/output/gfx-map.json`, `edited/Gxx.bin` | Redrawn picture text (if stage 03b ran) |
| 3 | `../../_config/rom-facts.md` | Font, free space, pointers |
| 3 | `../../_config/legal.md` | Sharing rules |
| 3 | `references/patch-instructions-template.md` | Template for the instructions |

## Process
1. Run `check_lengths.py`. Stop if anything overflows.
2. Run `insert_text.py` to write `output/patched.sfc`.
2b. Before you rewrite a code reference to text (`LDX #address`), check that the bank the code sets next to it
   (`LDA #bank`) is the text bank. Never rewrite a value that points into graphics: one such rewrite crashed a
   screen in the first run.
3. If the font has no Latin letters, add them (new tiles, then update the table). Record the change in `rom-facts.md`.
4. If text needs more room, add repointing or ROM expansion. Say what you changed and why.
4b. Pack each edited graphics block from stage 03b with `gfx_pack.py` and put it in place of the
   original. A block that grew moves to free space, and the code that sets its address is changed.
4c. List every piece of code that reads a name table, and every message the code joins from parts (name + piece
   + name, a name before a line, a number between pieces). Give each a form that fits, and test each in Mesen with
   the longest names and with names of odd and even length (with letter pairs, an odd name leaves half a cell).
4d. Reuse a font glyph for new letters only if no dumped text uses it and stage 02's font-read log never reads it.
4e. After any code or layout change, check each screen it touches in Mesen, next to the original ROM. A change can
   be undone or overflowed by other code of the game.
5. Run `make_patch.py`, then `verify_patch.py`. Both must pass.
6. Fill the template to write `output/HOW-TO-PATCH.md`, using the CRC32 values.

## Outputs
| File | Content |
|---|---|
| `output/patched.sfc` | Patched ROM. Local only, never shared |
| `output/game.bps` | The patch to share |
| `output/HOW-TO-PATCH.md` | Patching instructions |

## Verify
- [ ] `verify_patch.py` says the patched result is identical to `patched.sfc`.
- [ ] Original CRC32 in the instructions matches `rom-facts.md`.
- [ ] `patched.sfc` was never edited by hand after the patch was made.
- [ ] Every rewritten code reference was checked against its bank (step 2b).
- [ ] Every name reader and joined message from step 4c is listed, with the screen where it was seen in Mesen.
- [ ] Every screen touched by a code or layout change was compared with the original ROM in Mesen (step 4e).
Write the results under `## Verify` in `output/build-notes.md`.

## Review gate
Tell the user to load `patched.sfc` in the emulator and check that it boots and the first screens show English. Wait for "go".
