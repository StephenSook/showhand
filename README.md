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

Start `tools/wsl/run_instrumented_sim.py` in the stock simulation environment, start `tools/wsl/run_sonic.sh`, select ZMQ mode, and run `tools/wsl/replay_soma_v3.py`. The replay requests support release through a Unix socket and starts its 50 Hz clock only after the simulator acknowledges the release. After the last frame, it sends a finish request with the expected final frame and requests 0.6 seconds of controller drain. The simulator exits its own loop, writes telemetry plus metadata, and acknowledges only after those artifacts are flushed. Failed replays send an abort instead. The replay precomputes every SOMA-to-SMPL conversion before it starts the clock. Its scheduler sleeps for most of each interval and uses a bounded 3 ms final pacing margin. The frozen 10 ms maximum-jitter gate is unchanged. Rendering is a separate pass so image generation cannot slow control:

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
| SOMA conversion before replay | 11.928240 s | 11.696682 s |
| 50 Hz replay wall time | 8.840054 s | 17.600003 s |
| Maximum 50 Hz publish jitter | 0.001810 s | 0.000732 s |
| Offline render wall time, end to end | 124.548010 s | 370.800000 s |
| Paired-frame extraction wall time | 4.035973 s | 6.036880 s |
| Metrics wall time | 1.098713 s | 1.955245 s |
| Tracking mean absolute error | 0.408799 rad | 0.485052 rad |
| Tracking p95 absolute error | 1.323946 rad | 1.119997 rad |
| Minimum root height | 0.178233 m | 0.189155 m |
| Maximum root tilt | 144.237400 degrees | 85.514896 degrees |
| Maximum contact-foot slip | 7.425263 m/s | 1.041916 m/s |
| Contact-foot slip time | 1.689912 s | 2.663078 s |
| Time out of balance | 3.658211 s | 10.734144 s |
| Falls | 4 | 14 |
| Deterministic threshold result | fail | fail |

Both clips failed the tracking p95, root height, root tilt, foot slip, time out of balance, and fall cutoffs. All metrics above come from replay intervals that began after the simulator acknowledged support release and ended before the simulator acknowledged completion. The metric computation is deterministic for a saved trace. The MuJoCo and SONIC executions are not claimed to reproduce identical trajectories across launches.

The first long GEM-X attempt was killed under the undocumented image-feature path. The first short attempt stopped after 86.663354 seconds with `ModuleNotFoundError: No module named 'sam_3d_body'`. The documented `--no-imgfeat` short run then produced pose files but failed at retargeting after 290.748189 seconds because the vendor BVH and USD files were Git LFS pointer text. The exact conversion error was `ValueError: could not convert string to float: 'size'`. Fetching those two LFS objects over HTTPS and running the saved-result retarget helper for 232.594339 seconds completed the stage.

The long replay also exposed real WSL scheduling failures. Four attempts exceeded the unchanged 10 ms publish-jitter limit, at 0.032240 s on frame 710, 0.142612 s on frame 333, 0.044585 s on frame 18, and 0.010615 s on frame 199. A different attempt passed replay timing but was rejected because its telemetry contained a 0.342198 s gap against a 0.050000 s maximum. The accepted run passed both validators after controller logs were moved to WSL-native storage and the bounded pacing margin was added. These failed attempts are plumbing history, not additional takes.

The visual verdicts, fusion outputs, and GPU costs are not reported here until a real Serverless Job reaches a terminal state and the returned bytes pass validation. The prior Nebius CLI credential expired at `2026-10-05T15:26:01Z`; that create attempt stopped before a job was created. A fresh browser confirmation is pending. No model output has been substituted.

## Residual evaluation

`config/residual_prereg.yaml` fixes the comparison before real labels exist. The primary result will be the paired difference between fused-judge and tracking-only Cohen kappa against outside human binary grades, with a whole-take paired percentile bootstrap and 10,000 replicates. The harness also reports agreement rates and confusion matrices.

The only current residual inputs are synthetic unit-test rows. Their numbers are intentionally not reported as results.

## Not done

- Stephen has not recorded the real takes.
- An outside grader has not supplied human accept or re-show labels.
- The pre-registered residual comparison therefore has no result.
- The stock Pexels clips cannot establish product accuracy or value.
- Cosmos L40S loadability is not claimed until the blocked cloud job runs.
