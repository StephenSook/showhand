# Showhand Phase 1

Showhand grades recorded takes of one in-place human move. It does not turn a video into a robot move. It runs a take through NVIDIA's stock pose, retargeting, and humanoid-control path, measures the replay, and identifies seconds that should be shown again.

Phase 1 uses two licensed Pexels clips only to test the plumbing. Every result below is labeled `PLUMBING TEST`. It is not evidence that Showhand agrees with a human grader or improves robot teaching.

## Ownership and credit

The stock NVIDIA path is:

1. NVIDIA GEM-X extracts a saved SOMA body sequence from the clip.
2. NVIDIA SOMA Retargeter runs `NewtonPipeline(skeleton, "soma", "unitree_g1")` and exports the parallel G1 joint-angle reference used for tracking metrics.
3. The saved SOMA sequence is converted to SMPL Protocol v3 and replayed at 50 Hz into NVIDIA GEAR-SONIC.
4. GEAR-SONIC controls the simulated Unitree G1 in its MuJoCo environment.

Showhand's own work is the offline replay adapter, per-step simulator instrumentation, offline render pass, deterministic metrics, fixed visual question, structured fusion request, grounding guard, take record, and pre-registered residual harness.

The SONIC policy does not consume the Newton retarget CSV. SONIC consumes the SMPL stream through its learned encoder. The Newton CSV is a post-retargeting reference for the tracking comparison.

## Frozen grading thresholds

The thresholds in `config/thresholds.yaml` were committed before the first graded run. The immutable threshold commit is `0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9`. The file SHA-256 is `206c194a8863e9a7aa2ac2c9bb88edff10271aad224d34194fad215fe2076b76`.

These are engineering cutoffs, not measured findings. They must not be tuned against the two Pexels clips.

## Model choice

The visual job is pinned to `nvidia/Cosmos-Reason1-7B`. Its Hugging Face model card lists the NVIDIA Open Model License, says the model accepts images and video, and says NVIDIA tested BF16 inference. The card reports H100, A100, and GB200 test hardware. NVIDIA's NIM support information gives a 24 GB BF16 memory requirement for the 7B model, so its weights and stated BF16 requirement fit a 48 GB L40S. Loadability on this exact L40S still has to be established by the job. The code fails closed if the model does not load or if any window does not return the required object.

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

GEM-X, GEAR-SONIC, and the MuJoCo simulation run inside WSL Ubuntu 24.04 using the environments installed under `/home/stephensookra/showhand/`. `NEBIUS_API_KEY` is read from the environment. No secret belongs in this repository.

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

The Nebius fetch script requests `logs --tail 1000` and extracts only the delimited, gzip-compressed JSON payload. Each injected image is checked against Nebius's 65,536-byte per-file limit before a job is created.

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

The visual verdicts, fusion outputs, and GPU costs are not reported here because no Serverless Job reached creation. The prior Nebius CLI credential expired at `2026-10-05T15:26:01Z`. A fresh no-browser authorization later timed out with `context deadline exceeded`, trace ID `d87414b7bf30576eb3a7b62a45f0fc39`. No model output has been substituted. Nebius GPU time and GPU cost are both zero.

## Residual evaluation

`config/residual_prereg.yaml` fixes the comparison before real labels exist. The primary result will be the paired difference between fused-judge and tracking-only Cohen kappa against outside human binary grades, with a whole-take paired percentile bootstrap and 10,000 replicates. The harness also reports agreement rates and confusion matrices.

The only current residual inputs are synthetic unit-test rows. Their numbers are intentionally not reported as results.

## Not done

- Stephen has not recorded the real takes.
- An outside grader has not supplied human accept or re-show labels.
- The pre-registered residual comparison therefore has no result.
- The stock Pexels clips cannot establish product accuracy or value.
- Cosmos L40S loadability is not claimed until the blocked cloud job runs.
- Exact runtime provenance for the external GEM-X and GEAR-SONIC installations was not captured for these plumbing runs.
