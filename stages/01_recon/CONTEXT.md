# Stage 01 — Recon

**Job:** Identify the ROM and find where the text and the font live.

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `input/*.sfc` or `*.smc` | The original ROM. Never modify it |
| 3 | `../../_config/rom-facts.md` | Fill in the blanks |
| 3 | `../../_config/tools.md` | Script usage |

## Process
1. Run `rom_info.py` on the ROM. Record header, size, map mode, CRC32.
2. Find text. Try `find_text.py --sjis` first. If it finds nothing, ask the user for any kana they see in the game (for example, a menu word) and run a relative search with `--word`.
3. If text is not found, test for compression or text drawn as tiles. Say so plainly and list next steps (a debugger emulator, a tile viewer).
4. Locate the font tiles if possible. Note format and whether it is fixed width.
5. Update `rom-facts.md`. Write `output/rom-report.md`: what was found, offsets, confidence (high/medium/low), and open questions.

## Outputs
| File | Content |
|---|---|
| `output/rom-report.md` | Findings, offsets, confidence, risks |
| `../../_config/rom-facts.md` | Updated facts |

## Verify
- [ ] Every offset in the report is a real file offset (with the header size noted).
- [ ] Each claim has a confidence level.
- [ ] CRC32 in `rom-facts.md` matches `rom_info.py` output.
Write the results under `## Verify` at the end of the report.

## Review gate
Tell the user to check: does the text sample in the report look like real game text? Do the offsets match what they see in the emulator? Wait for "go".
