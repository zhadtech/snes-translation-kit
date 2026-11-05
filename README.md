# SNES Translation Workspace

Translates an SNES game into English, one game per run.
You get a BPS patch, a patched ROM (local only), and patching instructions.

## Start a run (5 steps)
1. Open this folder in Claude Code (`cd snes-translation-kit && claude`).
2. Say: "Run the setup questionnaire." Answer the questions.
3. Copy your ROM into `stages/01_recon/input/`. It stays on your computer only.
4. Say: "Start stage 01." Review at each gate and say "go".
5. Play the patched ROM in your emulator. Write bugs in `stages/05_playtest/input/bug-notes.md`. Say: "Run stage 05."

To resume later, say: "Continue the run." Claude reads `PROGRESS.md`.

## Finished runs
Each finished run is copied to its own folder in `archive/`: the patch, notes, screenshots, and the scripts it used.
ROMs are never archived. Run folders in `archive/` are gitignored because they hold game text and graphics.

## Rules
- Share only `stages/04_build/output/game.bps` and `HOW-TO-PATCH.md`. Never share a ROM.
- Needs Python 3.

## About
An ICM (Interpretable Context Methodology) workspace: numbered stage folders, plain-markdown stage contracts, and
human review gates, run with Claude Code. The scripts were first built for one game (2-byte glyph codes,
a 12 x 12 font, LoROM); other games may need changed scripts.

## License
The scripts and workspace files are under the [MIT License](LICENSE).

This repo holds no ROMs and no game data. Game names, text, and graphics belong to their rights holders.
You must own a legal copy of any game you translate.
