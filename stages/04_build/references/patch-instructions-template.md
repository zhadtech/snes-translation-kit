# How to patch — {{PATCH_NAME}} {{VERSION}}

{{CREDIT}}

This patch changes a {{SOURCE_LANGUAGE}} SNES game into English. It does not contain the game. You must have your own copy of the original ROM.

## You need
- Your original ROM of *{{GAME_TITLE}}* ({{SOURCE_LANGUAGE}}).
  - Expected CRC32: `{{ORIGINAL_CRC32}}`
  - Expected file size: {{ORIGINAL_SIZE}} bytes
  - If your ROM has a 512-byte copier header, remove it first.
- A BPS patcher, such as Floating IPS (Flips) or Rom Patcher JS (runs in a web browser).
- An emulator or a flash cart.

## Steps
1. Make a copy of your original ROM. Keep the original safe.
2. Open the patcher. Choose `game.bps` as the patch and your ROM as the source.
3. Save the output as a new file, for example `{{OUTPUT_NAME}}.sfc`.
4. Check the result. The CRC32 should be `{{PATCHED_CRC32}}`.
5. Open the new file in your emulator.

## If it fails
- "Wrong source" or checksum error: your ROM is not the expected one. Check the CRC32 and the header.
- The game starts but the text is wrong: your ROM may be a different version.

## Known issues
{{KNOWN_ISSUES}}
