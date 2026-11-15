"""Turn the recorded frames into a 30 s, 1080p, 30 fps MP4 with crossfades."""
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
FR = HERE / "frames"
FPS = 30
XF = 0.5  # crossfade between scenes, s
TOTAL = 30.0

# scene, keep from, keep to (s, from the start of its recording); the last one is cut to make TOTAL
CUTS = [("1_intro", 0.0, 7.3), ("2_jijel", 0.3, 8.6), ("3_okavango", 0.3, 8.2), ("4_mexico", 0.0, None)]


def run(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


def segment(name):
    d = json.loads((FR / name / "index.json").read_text())
    fr, start, end = d["frames"], d["start"], d["end"]
    lines = []
    lead = fr[0][1] - start
    for i, (f, ts) in enumerate(fr):
        nxt = fr[i + 1][1] if i + 1 < len(fr) else end
        dur = (nxt - ts) + (lead if i == 0 and lead > 0 else 0)
        lines += [f"file '{(FR / name / f).as_posix()}'", f"duration {max(dur, 0.001):.4f}"]
    lines.append(f"file '{(FR / name / fr[-1][0]).as_posix()}'")
    lst = FR / f"{name}.txt"
    lst.write_text("\n".join(lines))
    out = HERE / f"seg_{name}.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "14", str(out))
    return out, end - start


segs = [segment(n) for n, _, _ in CUTS]
lens = []
for (n, a, b), (_, full) in zip(CUTS, segs):
    lens.append((b if b is not None else full) - a)
# the last scene absorbs the difference so the video is exactly TOTAL
lens[-1] = TOTAL - (sum(lens[:-1]) - XF * (len(lens) - 1))
assert lens[-1] <= segs[-1][1] - CUTS[-1][1] + 1e-6, f"last scene too short: needs {lens[-1]:.2f}s"

inputs, parts = [], []
for i, ((n, a, _), (path, _)) in enumerate(zip(CUTS, segs)):
    inputs += ["-i", str(path)]
    parts.append(f"[{i}:v]trim=start={a}:duration={lens[i]:.3f},setpts=PTS-STARTPTS,fps={FPS}[v{i}]")
chain, prev, off = [], "v0", 0.0
for i in range(1, len(segs)):
    off += lens[i - 1] - XF
    chain.append(f"[{prev}][v{i}]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{i}]")
    prev = f"x{i}"
chain.append(f"[{prev}]fade=t=in:st=0:d=0.4,fade=t=out:st={TOTAL - 0.5}:d=0.5,format=yuv420p[out]")
graph = ";".join(parts + chain)
out = HERE / "saraura_demo_30s.mp4"
run(*inputs, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex", graph, "-map", "[out]", "-map", f"{len(segs)}:a",
    "-t", f"{TOTAL}", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out))
print("scene lengths", [round(x, 2) for x in lens], "->", out)
