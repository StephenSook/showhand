# Showhand Phase 1

Showhand grades recorded takes of one in-place human move. It does not turn a video into a robot move. It runs a take through NVIDIA's stock pose, retargeting, and humanoid-control path, measures the replay, and identifies seconds that should be shown again.

**Watch the three graded takes: <https://showhand-replay.vercel.app>.** Each phone recording plays beside the simulated G1 that replayed it, with every measured second, both vision verdicts, every Nemotron answer the guard refused or passed, and the seconds sent back. No physical robot was used. The page is built from this repository's committed take records ([`web/`](web/README.md)).

Phase 1 used two licensed Pexels clips only to test the plumbing. Those results are labeled `PLUMBING TEST`. Stephen then recorded three takes of his own on a phone, and they ran through the same pipeline. Neither set is evidence that Showhand agrees with a human grader or improves robot teaching. One outside grader has since labeled Stephen's three takes, and disagreed with Showhand on all three (see [Residual evaluation](#residual-evaluation)).

## Ownership and credit

The stock NVIDIA path is:

1. NVIDIA GEM-X extracts a saved SOMA body sequence from the clip.
2. NVIDIA's SOMA retargeter (its Newton pipeline from SOMA to the Unitree G1, inside NVIDIA's code) turns the saved body sequence into the parallel G1 joint-angle reference used for tracking metrics. This repo calls it through the saved-result helper `run_retarget` in `tools/wsl/finish_gemx_retarget.py`.
3. The saved SOMA sequence is converted to SMPL Protocol v3 and replayed at 50 Hz into NVIDIA GEAR-SONIC.
4. GEAR-SONIC controls the simulated Unitree G1 in its MuJoCo environment.

Showhand's own work is the offline replay adapter, per-step simulator instrumentation, offline render pass, deterministic metrics, fixed visual question, structured fusion request, grounding guard, take record, and pre-registered residual harness.

The SONIC policy does not consume the Newton retarget CSV. SONIC consumes the SMPL stream through its learned encoder. The Newton CSV is a post-retargeting reference for the tracking comparison.

## Frozen grading thresholds

The thresholds in `config/thresholds.yaml` were committed before the first graded run. The immutable threshold commit is `0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9`. The file SHA-256 is `206c194a8863e9a7aa2ac2c9bb88edff10271aad224d34194fad215fe2076b76`.

These are engineering cutoffs, not measured findings. They must not be tuned against the two Pexels clips.

## Model choice

The visual job is pinned to `nvidia/Cosmos-Reason1-7B`. Its Hugging Face model card lists the NVIDIA Open Model License, says the model accepts images and video, and says NVIDIA tested BF16 inference. The card reports H100, A100, and GB200 test hardware. NVIDIA's NIM support information gives a 24 GB BF16 memory requirement for the 7B model; one L40S GPU has 48 GB of GPU memory. The job runs as a Nebius AI Cloud Serverless Job on platform `gpu-l40s-a` with preset `1gpu-8vcpu-32gb` (one L40S, 8 vCPUs, 32 GB of host RAM; `tools/cosmos_job/submit.sh`), and it loaded the model in 282 to 283 s on each of Stephen's three takes (`results/takes/take_*/visual_summary.json`, `timing.model_load_s`). The code fails closed if the model does not load or if any window does not return the required object.

Sources:

- <https://huggingface.co/nvidia/Cosmos-Reason1-7B>
- <https://docs.nvidia.com/nim/vision-language-models/latest/support-matrix.html>

Fusion is pinned to `nvidia/Nemotron-3_5-Lightning` on Nebius Token Factory. The request uses temperature 0, `enable_thinking: false`, and strict JSON Schema. The deterministic guard rejects uncited evidence, out-of-range windows, non-negative support, and reason text that does not exactly match a cited failure code.

## Installation

The local metrics and fusion package runs on Windows Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
```

GEM-X, GEAR-SONIC, and the MuJoCo simulation run inside WSL Ubuntu 24.04 using the environments installed under `/home/stephensookra/showhand/`. The GEM-X and replay logs of all three of Stephen's takes (in the ignored `artifacts/runs/<take>/logs/` folder) show NVIDIA Warp finding one CUDA device there, an `NVIDIA GeForce RTX 2070 SUPER` with 8 GiB. Each take's stage times are in `results/takes/<take>/driver/stage_timings.json`. `NEBIUS_API_KEY` is read from the environment. No secret belongs in this repository.

## Pipeline commands

Run GEM-X offline:

```bash
bash tools/wsl/run_gemx_offline.sh CLIP OUTPUT_ROOT
```

Start `tools/wsl/run_instrumented_sim.py` in the stock simulation environment, start `tools/wsl/run_sonic.sh LOG_DIRECTORY RUN_ID`, select ZMQ mode, and run `tools/wsl/replay_soma_v3.py` with the same `--run-id`. The SONIC wrapper refuses an existing log directory and captures its own fresh console log between exact run-boundary markers. The publisher waits 0.5 seconds for the stock ZMQ subscriber before requesting support release through a Unix socket. Its 50 Hz clock starts only after the simulator acknowledges that release. Publish-loop failures send an abort. After the last frame, the replay sends a finish request with the expected final frame and requests 0.6 seconds of controller drain. The simulator exits its own loop, writes telemetry and metadata through separate flushed temporary files, replaces each artifact sequentially, hashes the telemetry bytes, and acknowledges after both replacements. The metrics gate requires the run ID to match across replay timing, simulator metadata, and the SONIC launch log. It also requires SONIC's log between the matching run boundaries to contain every Protocol v3 frame index in exact order, binds the telemetry bytes, final timestamp, and row count to the acknowledgement, and grades the drain against the final target pose. The replay derives its code commit and clean-tree state from Git. The take-record writer rejects decisive artifacts without content hashes and verifies that the replay timing refers to an existing commit. The replay precomputes every SOMA-to-SMPL conversion before it starts the clock. Its scheduler sleeps for most of each interval and uses a bounded 3 ms final pacing margin. The frozen 10 ms maximum-jitter gate is unchanged. Rendering is a separate pass so image generation cannot slow control:

```bash
python tools/wsl/render_sim_telemetry.py \
  --telemetry TELEMETRY.csv \
  --replay-timing REPLAY_TIMING.json \
  --render RENDER.mp4 \
  --render-timestamps RENDER_TIMESTAMPS.csv \
  --render-meta RENDER_META.json
```

Compute the deterministic grade:

```powershell
.venv\Scripts\showhand metrics `
  --retarget-csv RETARGET.csv `
  --source-fps 25 `
  --telemetry TELEMETRY.csv `
  --replay-timing REPLAY_TIMING.json `
  --sim-meta SIM_META.json `
  --sonic-console SONIC_CONSOLE.log `
  --thresholds config\thresholds.yaml `
  --out METRICS.json
```

Build paired frames, submit the visual job, fetch its raw structured results, and run fusion:

```bash
bash tools/cosmos_job/submit.sh TAKE_ID PAIRS_DIR
bash tools/cosmos_job/fetch.sh JOB_ID TAKE_ID PAIRS_DIR/manifest.json OUTPUT_JSON
```

```powershell
.venv\Scripts\showhand fusion --metrics METRICS.json --visual VISUAL.json --out FUSION.json
.venv\Scripts\showhand write-record --input RECORD_INPUT.json --out TAKE_RECORD.json
```

The Nebius fetch script requests `logs --tail 1000` and extracts only the delimited, gzip-compressed JSON payload. Nebius allows 65,536 bytes of injected files per job in total, and `submit.sh` refuses a set over that before creating a job. One take's pairs are about 300 KB, so set `PAIRS_BUCKET` to a private Object Storage bucket that holds the pairs under `TAKE_ID/`; the job then mounts it read-only. The validator accepts only `COMPLETED`, the state Nebius documents as a successful job.

## PLUMBING TEST results

These outputs come from Pexels stock clips. They are not product evidence.

| Field | `pexels_5510095` | `pexels_5510143` |
| --- | ---: | ---: |
| Source frames at 25 fps | 222 | 441 |
| Target motion duration | 8.84 s | 17.60 s |
| GEM-X and retarget wall time | 523.342528 s across recovery steps | 722.984161 s |
| Run ID | `pexels_5510095-20261005-ff05d94-r1` | `pexels_5510143-20261005-ff05d94-r1` |
| Showhand commit, clean at replay start | `ff05d94053023bce7d5b4dc17d6ad581ba4c1604` | `ff05d94053023bce7d5b4dc17d6ad581ba4c1604` |
| SOMA conversion before replay | 6.672334 s | 10.174046 s |
| 50 Hz replay wall time | 8.840001 s | 17.600002 s |
| Maximum 50 Hz publish jitter | 0.005299 s | 0.001185 s |
| SONIC Protocol v3 frames received | 443 of 443, 0 through 442 | 881 of 881, 0 through 880 |
| Post-roll included in grading | 0.605870 s | 0.605106 s |
| Offline render wall time, end to end | 130.990000 s | 234.790000 s |
| Paired-frame extraction wall time | 2.610044 s | 4.074039 s |
| Metrics wall time | 0.919013 s | 1.023692 s |
| Tracking mean absolute error | 0.529236 rad | 0.485284 rad |
| Tracking p95 absolute error | 1.272042 rad | 1.119977 rad |
| Minimum root height | 0.189993 m | 0.189966 m |
| Maximum root tilt | 85.342885 degrees | 85.422806 degrees |
| Maximum contact-foot slip | 0.989901 m/s | 0.989901 m/s |
| Contact-foot slip time | 1.372307 s | 2.757829 s |
| Time out of balance | 5.984513 s | 11.291179 s |
| Falls | 7 | 14 |
| Deterministic threshold result | fail | fail |

Both clips failed the tracking p95, root height, root tilt, foot slip, time out of balance, and fall cutoffs. The short clip also failed the tracking mean cutoff. All metrics above begin after the simulator acknowledged support release and include the measured controller drain after the final publish. The metric computation is deterministic for a saved trace. The MuJoCo and SONIC executions are not claimed to reproduce identical trajectories across launches.

The recorded clean commit covers this Showhand repository at replay start. These two plumbing runs did not capture runtime commits or input hashes for the external GEM-X and GEAR-SONIC trees, controller executable, policy weights, planner, or observation configuration. The take records hash the saved GEM-X outputs, replay inputs, controller log, simulator telemetry, render, metrics, and manifests. They must not be read as proof of the exact external stock-stack version.

The first long GEM-X attempt was killed under the undocumented image-feature path. The first short attempt stopped after 86.663354 seconds with `ModuleNotFoundError: No module named 'sam_3d_body'`. The documented `--no-imgfeat` short run then produced pose files but failed at retargeting after 290.748189 seconds because the vendor BVH and USD files were Git LFS pointer text. The exact conversion error was `ValueError: could not convert string to float: 'size'`. Fetching those two LFS objects over HTTPS and running the saved-result retarget helper for 232.594339 seconds completed the stage.

The long replay also exposed real WSL scheduling failures. Four attempts exceeded the unchanged 10 ms publish-jitter limit, at 0.032240 s on frame 710, 0.142612 s on frame 333, 0.044585 s on frame 18, and 0.010615 s on frame 199. A different attempt passed replay timing but was rejected because its telemetry contained a 0.342198 s gap against a 0.050000 s maximum. Another replay passed those gates but was withdrawn when the stronger receipt validator found that SONIC logged frames 5 through 880 instead of 0 through 880. The accepted run passed all validators after controller logs were moved to WSL-native storage, the bounded pacing margin was added, and the publisher warmup was introduced. These failed attempts are plumbing history, not additional takes.

For these two plumbing clips, the visual verdicts, fusion outputs, and GPU costs are not reported because no Serverless Job reached creation for them. Stephen's takes below did run through the Nebius job. The prior Nebius CLI credential expired at `2026-10-05T15:26:01Z`. A fresh no-browser authorization later timed out with `context deadline exceeded`, trace ID `d87414b7bf30576eb3a7b62a45f0fc39`. No model output has been substituted. Nebius GPU time and GPU cost are both zero.

## Stephen's takes

Stephen recorded three takes (`IMG_0525` to `IMG_0527`) on a phone at 30 fps on 2026-10-05. Each ran through `tools/wsl/run_take.sh`: GEM-X, SOMA to G1 retargeting, the 50 Hz SONIC replay in MuJoCo, the offline render, a side-by-side clip of source and simulation, and the deterministic grade against the frozen thresholds. The source videos and full run folders stay under the ignored `artifacts/` folder and are not committed.

The sanitized text records are documented in [`results/takes/`](results/takes/README.md). The replay and deterministic numbers below come from the committed `replay_timing.json` and `metrics.json` files. The visual values come from the allowlisted [`take_0525`](results/takes/take_0525/visual_summary.json), [`take_0526`](results/takes/take_0526/visual_summary.json), and [`take_0527`](results/takes/take_0527/visual_summary.json) summaries. The [`take_0525`](results/takes/take_0525/final_state.json), [`take_0526`](results/takes/take_0526/final_state.json), and [`take_0527`](results/takes/take_0527/final_state.json) final-state records point from the stale historical records to the later stage outputs. Fusion status, decision, request ids, and cost come from `fusion.json`.

| Field | `take_0525` | `take_0526` | `take_0527` |
| --- | ---: | ---: | ---: |
| Source frames at 30 fps | 184 | 187 | 178 |
| Target motion duration | 6.1 s | 6.2 s | 5.9 s |
| Run ID | `take0525-20261005-c6847f2-r1` | `take0526-20261005-c82fdba-r1` | `take0527-20261005-c82fdba-r1` |
| Showhand commit, clean at replay start | `c6847f2` | `c82fdba` | `c82fdba` |
| 50 Hz frames published | 306 | 311 | 296 |
| Maximum 50 Hz publish jitter | 0.000039 s | 0.000086 s | 0.000103 s |
| Publish deadline misses | 0 | 0 | 0 |
| Tracking mean absolute error | 0.240200 rad | 0.221003 rad | 0.232949 rad |
| Tracking p95 absolute error | 0.695321 rad | 0.603113 rad | 0.716256 rad |
| Minimum root height | 0.473044 m | 0.756251 m | 0.481920 m |
| Maximum root tilt | 23.134581 degrees | 7.273088 degrees | 23.326847 degrees |
| Maximum contact-foot slip | 1.486444 m/s | 1.546044 m/s | 0.979841 m/s |
| Contact-foot slip time | 0.784643 s | 0.365411 s | 0.489463 s |
| Time out of balance | 1.275880 s | 0.552972 s | 0.526571 s |
| Falls | 0 | 0 | 0 |
| Deterministic threshold result | fail: foot slip, out of balance | fail: out of balance | fail: out of balance |
| Seconds that fail on their own | 1 to 2 (tracking p95) | 0 to 1 (out of balance), 2 to 3 (tracking p95) | none |

The simulated G1 stayed up on all three takes, against 7 and 14 falls on the Pexels clips. All three still fail the whole-take cutoffs. `take_0526` and `take_0527` are over the 0.50 s out-of-balance cutoff by 0.053 s and 0.027 s. `take_0527` has no single failing second: its out-of-balance time only crosses the cutoff when the seconds are added up. The per-second rows are the re-show candidates the grade produces.

These are Showhand's measurements of a simulated replay. They do not say whether a human grader would accept the take, and the thresholds were not changed after these runs.

### Visual judge and fusion on Stephen's takes

The accepted summaries record `nvidia/Cosmos-Reason1-7B`, exact model-load times, and each window's verdict and latency. They do not record a Nebius job id, job state, GPU type, GPU seconds, job wall time, price source, or GPU cost. The existing L40S, job-id, wall-time, and about $0.38 claims remain unverified until the original Nebius job metadata is recovered.

| Field | `take_0525` | `take_0526` | `take_0527` |
| --- | --- | --- | --- |
| Cosmos windows that match | 6 of 7 | 7 of 7 | 5 of 6 |
| Cosmos mismatch | 4 to 5 s: upper body, lower body, orientation | none | 3 to 4 s: upper body, lower body, orientation |
| Nebius job, not in accepted records | `aijob-e00d1f0neh67r4nnrt` | `aijob-e00dpjhqxkn5xgvb76` | `aijob-e00xc8v043dvrrdgn5` |
| Fusion status | deterministic fallback after 2 guard refusals | passed after one retry | passed after one retry |
| Fused decision | re-show 1 to 2 s and 4 to 5 s | re-show 0 to 1 s | re-show 3 to 4 s |
| Token Factory request ids | `5f8b02c559b5532e97fc393dd83d92cd`, `55e67f4ad5ca373c73f65c11b0934400` | `ef1546107a4724d7d1585335e2afb568`, `639193fa38ca5f6abc8e276b697ab41d` | `17e8b467742ee10f7a3e250ebf86cd73`, `a455ed7681a48218f6ab822aa9aa8e9e` |
| Fusion cost | $0.00030144 | $0.00028386 | $0.00028020 |

The visual summaries support the first two rows. The fusion records support the final four rows. No accepted record supports the Nebius job row or the missing job-level resource and cost fields.

Both visual mismatches show the same thing in their frames: Stephen squats facing the camera while the G1 squats turned about 90 degrees. The deterministic grade has no yaw term, so this is a failure the visual judge sees and the metrics cannot.

The grounding guard refused the first Nemotron answer on every take. On `take_0526` and `take_0527` it answered accept while measured evidence failed. On `take_0525` it twice proposed re-showing 2 to 3 s, a second with no negative evidence. Told the refusal reason, Nemotron gave grounded windows for `take_0526` and `take_0527`; `take_0525` fell back to re-showing every negative window. Nemotron was not deterministic at temperature 0: an earlier run on `take_0525` (request `503cf0e1add30b7ca120deaabebf59ca`) passed on its first answer with re-show 1 to 2 s. The fused answers can also leave out a failing second: `take_0526`'s re-shows 0 to 1 s but not the failing 2 to 3 s. The retry and the fallback were added on 2026-10-06, before any outside grade existed, and are recorded as an amendment in `config/residual_prereg.yaml`.

## Second visual judge (Nemotron 3.5 Super VL on Token Factory)

`tools/supervl_judge.py` sends each original Cosmos window input to the open-weight NVIDIA-Nemotron-3.5-Super-VL-120B-A12B model through Nebius Token Factory as `nvidia/Nemotron-3.5-Super-VL`. It imports the same fixed question and schema validator used by the Cosmos job. Each invalid response fails closed for that window. This path calls the hosted API and needs no GPU job.

The recorded run covered 20 windows [MEASURED], all 20 of which returned valid schema objects [MEASURED]. Temperature was 0, but the model is not assumed to be deterministic and no prompt or threshold was tuned against these results.

| Take | Valid windows | Cosmos vs Super VL | Cosmos vs deterministic | Super VL vs deterministic | Super VL cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `take_0525` | 7 of 7 [MEASURED] | 1 of 7, 14.2857% [MEASURED] | 5 of 7, 71.4286% [MEASURED] | 1 of 7, 14.2857% [MEASURED] | $0.0016299 [MEASURED] |
| `take_0526` | 7 of 7 [MEASURED] | 1 of 7, 14.2857% [MEASURED] | 5 of 7, 71.4286% [MEASURED] | 1 of 7, 14.2857% [MEASURED] | $0.0016191 [MEASURED] |
| `take_0527` | 6 of 6 [MEASURED] | 1 of 6, 16.6667% [MEASURED] | 5 of 6, 83.3333% [MEASURED] | 0 of 6, 0.0000% [MEASURED] | $0.0014535 [MEASURED] |
| Overall | 20 of 20 [MEASURED] | 3 of 20, 15.0% [MEASURED] | 15 of 20, 75.0% [MEASURED] | 2 of 20, 10.0% [MEASURED] | $0.0047025 [MEASURED] |

The verdict counts and costs come from the three committed `supervl_summary.json` files. The agreement counts come from [`results/judge_agreement.json`](results/judge_agreement.json), which compares both visual verdicts with the committed deterministic per-second grades. These are judge-to-judge comparisons, not agreement with a human grader.

The private frames were sent only to Nebius Token Factory, whose inference service runs in [zero-retention mode](https://nebius.com/services/token-factory/enterprise-grade-inference), and were never committed. The committed summaries contain verdict text, request ids, timing, token counts, and cost, but no image bytes, data URLs, or local image paths.

## Residual evaluation

`config/residual_prereg.yaml` fixes the comparison before real labels exist. The primary result will be the paired difference between fused-judge and tracking-only Cohen kappa against outside human binary grades, with a whole-take paired percentile bootstrap and 10,000 replicates. The harness also reports agreement rates and confusion matrices.

**The first outside grades.** On 2026-10-21 an outside robotics builder, shown each emailed clip (the phone take beside the simulated G1) and asked for keep or redo, kept all three: [`results/residual/human_grades.json`](results/residual/human_grades.json). `python tools/residual_report.py` applies the pre-registration and writes [`results/residual/report.json`](results/residual/report.json):

| Judge | Agrees with the human | Confusion |
|---|---|---|
| Fused judge (Showhand's decision) | 0 of 3 | human kept 3, judge re-showed 3 |
| Tracking error alone (the baseline) | 3 of 3 | human kept 3, judge kept 3 |

The primary result is `evaluation_invalid`, which is what `observed_undefined_kappa` says to do: the human and the tracking-only judge gave every take the same grade, so that judge's Cohen kappa is undefined (the fused judge's is 0). Read plainly: on these three takes a human watching the clip let all of them through, and so did tracking error, while Showhand sent seconds back on every one, for balance (0.53 to 1.28 s out of balance against 0.5 s), foot slip, a 1.411 rad joint-error peak and Cosmos pose mismatches. Three takes from one grader say nothing about which is right for training data, and nothing here was tuned after the grades arrived. The synthetic unit-test rows are still never reported as results.

## Not done

- One outside grader on three takes. The pre-registered comparison needs takes the human and both judges do not all grade alike before it has a valid result.
- The stock Pexels clips cannot establish product accuracy or value.
- The two Pexels plumbing clips have no visual verdicts; the jobs above covered Stephen's takes only.
- The historical take records for Stephen's takes still list the visual judge as blocked. The committed `final_state.json` files point to the later visual and fusion outcomes without asserting unsupported job ids.
- Exact runtime provenance for the external GEM-X and GEAR-SONIC installations was not captured for these plumbing runs.
