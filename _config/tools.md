# Tools

TODO(setup): answer Group 2 of `setup/questionnaire.md`: confirm the emulators below are still installed, and
give the new ROM's file name.

## Installed
- Python 3 (tested with 3.13 on macOS). Run scripts as `python3 scripts/<name>.py`. No extra packages needed.

## Emulator
- Any SNES emulator can play the patched ROM.
- Debugger emulator: **MesenCE** (Mesen 2, from github.com/nesdev-org/MesenCE). `scripts/mesen_shots.py` finds it
  from `--mesen`, `$MESEN`, `~/Downloads/Mesen.app` or `/Applications/Mesen.app`.
- **Controller:** if SNES port 1 is "None" in Mesen settings, the game gets no buttons.
  To play: Settings → Input → SNES → Port 1 → "SNES Controller", then set the keys.
- **Headless runs** (no window): `Mesen --testrunner ROM script.lua --timeout=N --doNotSaveSettings
  --snes.port1.type=SnesController`. The last switch plugs in a controller for that run only.
  Lua file access (`io`) is off in the sandbox, so scripts print data to stdout instead.
  `scripts/mesen_shots.py` wraps this. About 250 frames per second.
- ROM file: TODO (in `stages/01_recon/input/`). Never modify it.
- Save states help play-testing: save before each scene so you can reload quickly.

## Scripts (all in `scripts/`)
| Script | Use |
|---|---|
| `rom_info.py ROM` | Header, size, map mode, checksums |
| `find_text.py ROM --word かな` | Relative search for a known word |
| `find_text.py ROM --sjis` | Find Shift-JIS runs |
| `dump_text.py ROM TBL BLOCKS OUTDIR` | Dump blocks to JSON (fixed slots: `record_bytes`, or `slots` with each line's cells; code operands: `operands`) |
| `check_lengths.py TBL TRANSLATED_DIR [--map BUILD_MAP]` | Check lines fit; with `--map`, also the letter-pair limits of the sentence blocks (rows per box, name tokens, a name drawn before a line, script lines, code-joined bar messages, missing narrow letters, pair count) |
| `narrow_text.py` (module) | The letter-pair layout rules shared by `build_rom.py` and `check_lengths.py` |
| `insert_text.py ROM TBL TRANSLATED_DIR OUT` | Write text into a copy of the ROM |
| `make_patch.py ORIGINAL PATCHED OUT.bps` | Make a BPS patch |
| `verify_patch.py ORIGINAL PATCH PATCHED` | Apply the patch and compare |
| `build_rom.py ROM EXTRACT_DIR TRANSLATED_DIR MAP OUT` | Pack moved text, fix pointers, code bytes, checksum (stage 04) |
| `mesen_shots.py ROM OUTDIR --shots F1,F2 [--input "700-705:start"]` | Run Mesen headless, press buttons, save screenshots |
| `gfx_unpack.py ROM lz\|rle\|raw OFFSET OUTDIR [--bpp 4] [--cgram FILE --palette N] [--size N]` | Unpack a graphics block (raw: tiles stored unpacked, `--size` bytes); write `.bin` and a `.png` tile sheet (stage 03b) |
| `gfx_pack.py lz\|rle IN.bin OUT.bin [--rom ROM --offset OFFSET]` | Pack a block, check the round trip, compare with the original size (stages 03b, 04) |
| `gfx_draw.py find ROM TBL BIN BPP` / `draw ROM TBL MAP OUTDIR [ID ...]` | Find text drawn with the game's 12 x 12 font in a block; draw the English labels listed in `gfx-map.json` (stage 03b): placed by font match or by hand (`at`, `grid`), with options for two-tone and styled text (`outline`, `border`, `shadow`, `shade`, `shade_rows`, `fill: near` for text on a picture, `checker` for a dithered box) and tile map edits (`map_edits`) |

Run a script with no arguments to see its usage.

The scripts were written for the last game (2-byte glyph codes, a 12 x 12 font, LoROM, its graphics packers). A game
with another text system or language may need new or changed scripts. Each finished run keeps a
copy of the scripts it used in its folder under `archive/`.
