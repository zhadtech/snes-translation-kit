"""Run a ROM in Mesen with no window, press buttons on a schedule, and save screenshots.

usage: mesen_shots.py ROM OUTDIR --shots F1,F2,... [--input SCHEDULE] [--mesen PATH] [--timeout SEC]

SCHEDULE is comma-separated FRAME[-LAST]:BUTTONS, buttons joined by '+'
(a b x y l r up down left right start select). Example: "700-705:start,900:down+a".
Screenshots are saved as OUTDIR/shot_FFFFF.png. The run stops after the last shot.
Mesen is found from --mesen, $MESEN, ~/Downloads/Mesen.app or /Applications/Mesen.app.
Mesen's script sandbox has no file access, so the Lua side prints each PNG as hex on stdout.
"""
import argparse
import os
import subprocess
import sys
import tempfile

LUA = r"""
local shots = {%(shots)s}
local inputs = {%(inputs)s}
local last = %(last)d
local frames = 0
local function hex(s) return (s:gsub('.', function(c) return string.format('%%02x', c:byte()) end)) end
emu.addEventCallback(function()
  local pad = inputs[frames]
  if pad then emu.setInput(pad, 0) end
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  frames = frames + 1
  if shots[frames] then print("SHOT " .. frames .. " " .. hex(emu.takeScreenshot())) end
  if frames >= last then emu.stop(0) end
end, emu.eventType.endFrame)
"""

BUTTONS = {"a", "b", "x", "y", "l", "r", "up", "down", "left", "right", "start", "select"}


def find_mesen(given):
    for path in (given, os.environ.get("MESEN"),
                 os.path.expanduser("~/Downloads/Mesen.app/Contents/MacOS/Mesen"),
                 "/Applications/Mesen.app/Contents/MacOS/Mesen"):
        if path and os.path.exists(path):
            return path
    sys.exit("Mesen not found: pass --mesen PATH or set $MESEN")


def parse_inputs(text):
    frames = {}
    for item in filter(None, (text or "").split(",")):
        when, _, buttons = item.partition(":")
        first, _, last = when.partition("-")
        names = buttons.split("+")
        if not set(names) <= BUTTONS:
            sys.exit(f"unknown button in {item!r}")
        for f in range(int(first), int(last or first) + 1):
            frames.setdefault(f, set()).update(names)
    return frames


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("rom")
    ap.add_argument("outdir")
    ap.add_argument("--shots", required=True)
    ap.add_argument("--input", default="")
    ap.add_argument("--mesen")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    shots = sorted(int(s) for s in args.shots.split(","))
    inputs = parse_inputs(args.input)
    lua = LUA % {
        "shots": ", ".join(f"[{f}]=true" for f in shots),
        "inputs": ", ".join(f"[{f}]={{{', '.join(f'{b}=true' for b in sorted(bs))}}}"
                            for f, bs in sorted(inputs.items())),
        "last": shots[-1],
    }
    os.makedirs(args.outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "shots.lua")
        with open(script, "w") as f:
            f.write(lua)
        # The switch plugs in a controller for this run only (settings are not saved).
        run = subprocess.run([find_mesen(args.mesen), "--testrunner", os.path.abspath(args.rom), script,
                              f"--timeout={args.timeout}", "--doNotSaveSettings",
                              "--snes.port1.type=SnesController"],
                             capture_output=True, text=True, errors="replace")
    saved = 0
    for line in run.stdout.splitlines():
        if line.startswith("SHOT "):
            _, frame, data = line.split(" ", 2)
            path = os.path.join(args.outdir, f"shot_{int(frame):05d}.png")
            with open(path, "wb") as f:
                f.write(bytes.fromhex(data.strip()))
            print(path)
            saved += 1
    if saved != len(shots):
        print(run.stdout[-2000:], run.stderr[-2000:], sep="\n")
        sys.exit(f"saved {saved} of {len(shots)} screenshot(s); Mesen exit code {run.returncode}")


if __name__ == "__main__":
    main()
