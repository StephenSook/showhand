# Showhand replay

A static page that plays each graded take's phone recording beside the simulated Unitree G1 that
replayed it, with every per-second grade, both vision verdicts, every Nemotron fusion attempt the
guard refused or passed, and the final re-show list. Vite, TypeScript and three.js, no backend.

## Run it

```sh
pnpm install
pnpm dev          # http://localhost:5173
pnpm test         # data checks, and that public/replay agrees with results/takes
pnpm build
pnpm e2e          # builds, serves on 127.0.0.1:4174, runs Chromium
```

## Where the data comes from

Everything under `public/replay/` is generated from this repository's own records.

| File | Written by | From |
| --- | --- | --- |
| `g1.glb` | `tools/replay_glb.py` | the G1 visual meshes, one node per kept geom, decimated to 10% |
| `<take>/frames.bin`, `<take>/replay.json` | `tools/replay_glb.py` | `tools/wsl/export_replay.py`, which runs MuJoCo forward kinematics on the replay's logged joint states at the video's 30 fps |
| `<take>/grades.json`, `index.json` | `tools/replay_grades.py` | `results/takes/<take>/` metrics, both visual summaries, `fusion.json`, `driver/stage_timings.json`, and `config/thresholds.yaml` |

```sh
# in WSL, with the GR00T simulation venv, once per take
python tools/wsl/export_replay.py --telemetry artifacts/runs/<take>/sim/telemetry.csv \
  --replay-timing artifacts/runs/<take>/replay_timing.json --out artifacts/replay/<take>
# on the host, with trimesh and fast_simplification
python tools/replay_glb.py --export artifacts/replay --web web/public/replay \
  --takes take_0525 take_0526 take_0527
python tools/replay_grades.py --results results/takes --web web/public/replay \
  --takes take_0525 take_0526 take_0527
```

`tests/assets.test.ts` fails if a re-export changes one file and not the others: frame hashes,
GLB node names, per-second grades against `metrics.json`, fusion attempts against `fusion.json`,
run times against `stage_timings.json` and the two visual summaries, and frame counts against
`replay_timing.json`. The Python test `tests/test_replay_grades.py` fails if a committed
`grades.json` differs from a fresh export.

## The phone recordings

Input media stays out of git (see the root `.gitignore`), so `<take>/source.mp4` is not committed.
The deployed site carries them, encoded from each take's run directory:

```sh
ffmpeg -y -i artifacts/runs/<take>/source.mp4 -an -vf scale=540:-2 -c:v libx264 -preset slow \
  -crf 28 -pix_fmt yuv420p -movflags +faststart web/public/replay/<take>/source.mp4
```

With the clips present, the video element is the page's clock. Without them (a fresh clone, or CI),
a timer drives the same replay and the page says the recording is not part of the build. The
browser tests check whichever case applies.
