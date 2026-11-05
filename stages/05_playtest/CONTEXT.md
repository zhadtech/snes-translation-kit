# Stage 05 — Playtest

**Job:** Turn the user's bug notes into tracked bugs, route each to the right stage, and fix them.

## Inputs
| Layer | Path | Use |
|---|---|---|
| 4 | `input/bug-notes.md` | The user's notes from playing `patched.sfc` |
| 4 | `../04_build/output/patched.sfc` | Not read by Claude; the user plays it |
| 4 | `../03_translate/output/translated/Bxx.json` | Look up the text by ID |
| 3 | `../../_config/style-guide.md` | Wording rules |
| 3 | `../../_config/glossary.md` | Fixed names |

## Process
1. Read `bug-notes.md`. Give each issue an ID `BUG-001` and find the source line ID (`Bxx-nnn`) if possible. Ask the user for a screenshot or exact words when the line is unclear.
2. Classify each bug: **wording** (to stage 03), **display** (cut off, garbled, wrong font, to stage 04), **crash** (to stage 04), **missed text** (to stage 02), or **picture** (text drawn as tiles, not with the font: to stage 03b).
3. Write `output/bugs.md`: ID, line ID, class, status.
4. Fix wording bugs in `translated/Bxx.json`. For other classes, say which stage to rerun.
5. After fixes, re-run stage 04 and ask the user to test again.
6. If the same kind of bug appears twice, change the glossary, style guide, or a stage contract.

## Outputs
| File | Content |
|---|---|
| `output/bugs.md` | Bug list with IDs, class, and status |
| `../03_translate/output/translated/Bxx.json` | Wording fixes |

## Verify
- [ ] Every bug has a class and a status.
- [ ] Every fixed bug names the line ID it changed.
Write the results under `## Verify` at the end of `bugs.md`.

## Review gate
Tell the user to re-test the fixed items. A run is done when a full play-through has no open bugs. Wait for "go".
