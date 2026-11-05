# SNES Translation (→ EN)

## What this is
An ICM workspace. It turns an SNES ROM into an English fan translation in 6 stages.
A human checks the output at each review gate. One run = one game, over many sessions.
Final output: a BPS patch, a patched ROM (local only), and `HOW-TO-PATCH.md`.

01_recon → 02_extract → 03_translate → 03b_graphics → 04_build → 05_playtest
(03b redraws text that is part of the graphics. 05 sends bugs back to 02, 03, 03b or 04.)

## Map
- `CONTEXT.md` — which stage to run for a task.
- `_config/` — shared rules: `rom-facts.md`, `glossary.md`, `style-guide.md`, `legal.md`, `tools.md`.
- `stages/NN_name/CONTEXT.md` — the contract for each stage.
- `scripts/` — `tbl.py` (table encode/decode), `rom_info.py` (ROM header), `find_text.py` (find text), `dump_text.py` (ROM → JSON), `check_lengths.py` (fit check), `narrow_text.py` (letter-pair rules), `insert_text.py` (JSON → ROM), `build_rom.py` (stage 04 build), `make_patch.py` (BPS), `verify_patch.py` (patch check), `mesen_shots.py` (emulator screenshots), `gfx_unpack.py` / `gfx_pack.py` / `gfx_draw.py` (packed graphics).
- `PROGRESS.md` — current run. `EDIT-LOG.md` — edits across runs.
- `archive/` — finished runs. Do not read unless asked.

## Rules
1. Before you work in a stage, read its `CONTEXT.md`. Load only its Inputs.
2. Write only to the paths in the stage's Outputs table.
3. Stop at each review gate (after 01, 02, 03b, 04 and 05). Say what to check. Wait for "go".
4. The files on disk are the truth. Use the edited file, not your memory of it.
5. IDs: block `B01`, line `B01-001`, bug `BUG-001`, graphics block `G01`. Keep them the same in every stage.
6. Update `PROGRESS.md` after each step. Note the block you stopped at.
7. When the user edits an output, add a line to `EDIT-LOG.md`.
8. Use the scripts for mechanical work (hex, bytes, lengths, patches). You do the judgment work: finding text, reading the encoding, translating.
9. Never modify the original ROM. Never put a ROM or patched ROM in git or in a share. Share only the `.bps`.
10. Stop servers and delete temp files that you started or made.
11. If `_config/` contains `TODO(setup)`, run `setup/questionnaire.md` first.

## Talk style
Simple English. Short sentences. Define a technical word the first time.
