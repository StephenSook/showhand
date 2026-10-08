# Stephen's take records

This directory contains text-only records for Stephen's three recorded takes. It does not
contain source media, extracted frames, rendered media, pose data, meshes, archives, or encoded
binary data. Only the allowlisted JSON records were considered. Every candidate was parsed and
checked before it was copied. Each committed file is smaller than 64 KB.

The records preserve two stages that did not update the same file. `take_record.json` was written
before the visual and fusion stages. It still reports that the visual job was blocked and fusion
did not run. The later `fusion.json` is the record of the Token Factory attempts and final guarded
decision. Read each record for the stage it actually captures.

## File map

| File | Contents |
| --- | --- |
| `take_record.json` | Aggregate replay provenance, deterministic metrics, artifact hashes, and the pre-visual stage status. |
| `metrics.json` | Whole-take and one-second deterministic measurements against the frozen thresholds. |
| `fusion.json` | Nemotron attempts, grounding-guard results, final decision, token usage, request ids, latency, and cost. |
| `replay_timing.json` | Replay run id, source and output counts, commit state, timing, jitter, and simulator receipt data. |
| `driver/stage_timings.json` | Driver wall times for GEM-X, replay, render, metrics, and record writing. |
| `driver/summary.json` | Compact driver summary for the replay run and deterministic result. |
| `sim/sim_meta.json` | Simulator receipt, telemetry binding, run id, and measurement definitions. |
| `sim/render_meta.json` | Offline render selection and timing metadata. Local input paths are redacted. |
| `sonic_logs/metadata.json` | SONIC log-boundary markers and the recorded robot configuration. |

## Run provenance

The replay run ids come from each copied `replay_timing.json`. The Token Factory request ids come
from each copied `fusion.json`.

| Take | Replay run id | Showhand commit at replay | Token Factory request ids |
| --- | --- | --- | --- |
| `take_0525` | `take0525-20261005-c6847f2-r1` | `c6847f2738f00fcea61dcf107325d6907034e28b` | `5f8b02c559b5532e97fc393dd83d92cd`, `55e67f4ad5ca373c73f65c11b0934400` |
| `take_0526` | `take0526-20261005-c82fdba-r1` | `c82fdbaaad4f7f9a11db9e097b8e2fad477d8bf1` | `ef1546107a4724d7d1585335e2afb568`, `639193fa38ca5f6abc8e276b697ab41d` |
| `take_0527` | `take0527-20261005-c82fdba-r1` | `c82fdbaaad4f7f9a11db9e097b8e2fad477d8bf1` | `17e8b467742ee10f7a3e250ebf86cd73`, `a455ed7681a48218f6ab822aa9aa8e9e` |

No Nebius visual job id is asserted in this directory. The only candidate record containing that
stage's job metadata was `visual.json`, and all three copies were rejected by the privacy check.

## Rejected records

- `take_0525/visual.json` was rejected because seven `pair_path` string values contained the
  forbidden `pairs` path segment.
- `take_0526/visual.json` was rejected because seven `pair_path` string values contained the
  forbidden `pairs` path segment.
- `take_0527/visual.json` was rejected because six `pair_path` string values contained the
  forbidden `pairs` path segment.

Nothing from those rejected files was copied into this directory.

## Local path replacements

The following keys contained absolute Windows or WSL paths. Their complete values were replaced
with the literal placeholder `"<local path>"` in each of the three take directories:

- `take_record.json`: `source.original_wsl_path`
- `replay_timing.json`: `source_pt`
- `driver/summary.json`: `render`, `take_record`
- `sim/render_meta.json`: `source_telemetry`, `source_replay_timing`

This made 18 replacements in total. Relative artifact references that passed the forbidden-segment
check remain in the copied records.
