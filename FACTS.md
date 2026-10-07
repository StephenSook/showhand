# FACTS

This is the code-audited fact sheet for Showhand. The README, the Devpost writeup, and the demo video narration draw from this file. A row is machine-checked when its tag is MEASURED and its source is a repo JSON or YAML path, a space, and a dotted key. Other rows are not machine-checked.

Tags:

- MEASURED: a committed file, or a command run for this sheet.
- SOURCED: an outside document with a URL. None of the outside pages named in the README were opened for this sheet. Those claims are NOT VERIFIED below.
- NOT VERIFIED: the value is not established here. The source cell says what check would verify it.

Read the source, not a retelling. Where the README and a committed file disagree, the file wins. Those cases are in [Drift found](#drift-found).

Audited on branch `facts-sheet` at `4913ad4e04e020a94fce724705e67eae70ccde1b` on 2026-10-07. `git rev-parse HEAD` printed that SHA before this file existed.

## What Showhand does

Showhand grades a recorded take of one in-place human move. The person records the move on a camera. NVIDIA's stock pose, retargeting, and humanoid-control programs drive a simulated Unitree humanoid through that move. Showhand measures the replay and returns accept or re-show, naming the seconds to show again. Showhand does not itself convert a video into a robot command.

## NVIDIA stock path and Showhand's own work

NVIDIA's stock path, as this repository invokes it, is the GEM-X offline demo, the saved-result SOMA retarget helper, and GEAR-SONIC in the GR00T whole-body control tree, which controls the simulated Unitree humanoid in MuJoCo. The retargeted joint table is the reference for tracking. SONIC is fed the converted body stream, not that table. The README also names a Newton pipeline constructor that takes the SOMA skeleton and the Unitree humanoid target. That call is not in this repository. The metrics code labels the retargeter with a Newton pipeline name. Showhand's own work is the offline replay adapter, the per-step simulator instrumentation, the offline render, the deterministic metrics, the fixed visual question, the structured fusion request, the grounding guard, the take record, and the pre-registered residual harness.

## Frozen thresholds

`config/thresholds.yaml` is the frozen cutoff file. Commit `0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9` (2026-10-05 13:41:40 -0400, subject "Freeze Showhand Phase 1 thresholds and scope") is the only commit that touches the file (`git log --follow --oneline -- config/thresholds.yaml`). The blob at that commit and the blob at HEAD are both `a46364cfd87e98a1b9ac6726f87d1e3b8c88eabc`. `git diff --stat` from that commit to HEAD for this file is empty. `sha256sum` of `git show 0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9:config/thresholds.yaml` and of the worktree file both printed `206c194a8863e9a7aa2ac2c9bb88edff10271aad224d34194fad215fe2076b76`. That commit is an ancestor of the first committed plumbing report `b9f940a80e953c2806fd82e4a1f9405464c5b10e` (2026-10-05 15:20:15 -0400) and of HEAD. `git merge-base --is-ancestor` exited 0 for both.

These cutoffs are engineering settings. They are not measured findings from the clips.

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| Threshold schema version | 1 | config/thresholds.yaml schema_version | MEASURED |
| Threshold file is frozen | true | config/thresholds.yaml frozen | MEASURED |
| Grading window length in seconds | 1.0 | config/thresholds.yaml window_seconds | MEASURED |
| Max tracking mean absolute error in radians | 0.5 | config/thresholds.yaml tracking.max_mean_abs_error_rad | MEASURED |
| Max tracking p95 absolute error in radians | 1.0 | config/thresholds.yaml tracking.max_p95_abs_error_rad | MEASURED |
| Fall root height in meters | 0.2 | config/thresholds.yaml balance.fall_root_height_m | MEASURED |
| Max root tilt in degrees | 35.0 | config/thresholds.yaml balance.max_root_tilt_deg | MEASURED |
| Max time out of balance in seconds | 0.5 | config/thresholds.yaml balance.max_out_of_balance_seconds | MEASURED |
| Support margin in meters | 0.02 | config/thresholds.yaml balance.support_margin_m | MEASURED |
| Foot half length in meters | 0.12 | config/thresholds.yaml balance.foot_half_length_m | MEASURED |
| Foot half width in meters | 0.06 | config/thresholds.yaml balance.foot_half_width_m | MEASURED |
| Contact speed threshold in meters per second | 0.1 | config/thresholds.yaml foot_slip.contact_speed_threshold_m_s | MEASURED |
| Max foot-slip time in seconds | 0.5 | config/thresholds.yaml foot_slip.max_slip_seconds | MEASURED |
| Any fall is a re-show | true | config/thresholds.yaml decision.any_fall_is_reshow | MEASURED |
| Any visual mismatch is a re-show | true | config/thresholds.yaml decision.any_visual_mismatch_is_reshow | MEASURED |
| Retargeter name stored by the metrics code | "NVIDIA SOMA Retargeter NewtonPipeline soma_to_unitree_g1" | src/showhand/metrics.py:14 | MEASURED |
| G1 joint names in the metrics tuple | 29 | command: Python ast count of G1_JOINT_NAMES in src/showhand/metrics.py | MEASURED |
| Frozen max telemetry gap in seconds | 0.05 | src/showhand/cli.py:123 | MEASURED |

The joint-name count is the length of the tuple, not a finding about a take. The telemetry gap constant is the gate in `src/showhand/cli.py`. The metrics default at `src/showhand/metrics.py:93` is the same `0.05`.

## Pre-registration

`config/residual_prereg.yaml` fixes the comparison before outside human grades exist. `sha256sum` of the worktree file printed `b0a7d011f4d790ac34ce38426ea59e329f24f659e812282c8b2b2ac5d49bd8d5`. The file's own history is three commits: `1092140` added the harness, `29f88b17e65c072fd7d244cb2bf22fc53eb31d17` (2026-10-05 15:41:31 -0400) defined bootstrap handling, and `9fb9c782af1010a6c414c534386d19fa7e4d226d` (2026-10-05 23:55:50 -0400) recorded the retry amendment. That local timestamp is 2026-10-06 03:55:50 UTC. The amendment date inside the file is `2026-10-06`.

The harness has no real-label result. `synthetic_data_policy` says unit tests only, and the status is still waiting for real takes and human grades. The amendment text inside the file states a refusal count. That sentence is part of the committed file. The fusion outputs it describes are not in the repo. See the NOT VERIFIED rows.

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| Pre-registration schema version | 1 | config/residual_prereg.yaml schema_version | MEASURED |
| Pre-registration status | "waiting_for_real_takes_and_human_grades" | config/residual_prereg.yaml status | MEASURED |
| Primary outcome | "cohen_kappa_with_outside_human_binary_grade" | config/residual_prereg.yaml primary.outcome | MEASURED |
| Primary treatment | "fused_judge" | config/residual_prereg.yaml primary.treatment | MEASURED |
| Primary baseline | "tracking_error_alone" | config/residual_prereg.yaml primary.baseline | MEASURED |
| Primary effect | "paired_cohen_kappa_difference" | config/residual_prereg.yaml primary.effect | MEASURED |
| Primary interval | "paired_bootstrap_percentile_95" | config/residual_prereg.yaml primary.interval | MEASURED |
| Bootstrap replicates | 10000 | config/residual_prereg.yaml primary.bootstrap_replicates | MEASURED |
| Bootstrap seed | 20261005 | config/residual_prereg.yaml primary.bootstrap_seed | MEASURED |
| Report each judge agreement rate | true | config/residual_prereg.yaml secondary.report_each_judge_agreement_rate | MEASURED |
| Report confusion matrices | true | config/residual_prereg.yaml secondary.report_confusion_matrices | MEASURED |
| Report n | true | config/residual_prereg.yaml secondary.report_n | MEASURED |
| Observed undefined kappa policy | "evaluation_invalid" | config/residual_prereg.yaml observed_undefined_kappa | MEASURED |
| Bootstrap undefined kappa policy | "discard_replicate" | config/residual_prereg.yaml bootstrap_undefined_kappa | MEASURED |
| Minimum valid bootstrap fraction | 0.95 | config/residual_prereg.yaml minimum_valid_bootstrap_fraction | MEASURED |
| Resampling unit | "whole_take" | config/residual_prereg.yaml resampling_unit | MEASURED |
| Missing labels policy | "reject" | config/residual_prereg.yaml missing_labels | MEASURED |
| Synthetic data policy | "unit_tests_only_never_report_as_results" | config/residual_prereg.yaml synthetic_data_policy | MEASURED |
| Amendment date | "2026-10-06" | config/residual_prereg.yaml amendments.0.date | MEASURED |
| Amendment says it is before any outside human grade | true | config/residual_prereg.yaml amendments.0.before_any_outside_human_grade | MEASURED |
| Amendment reason text | "On the first three real takes the grounding guard refused 2 of 3 Nemotron answers (accept against failing evidence), which left the fused judge without a decision." | config/residual_prereg.yaml amendments.0.reason | MEASURED |
| Amendment fused-judge procedure | ["one Nemotron answer, guarded", "if refused, one retry that is told the refusal reason, guarded", "if refused again, a deterministic re-show of every negative cited window", "fused_accept is the final decision of that procedure"] | config/residual_prereg.yaml amendments.0.fused_judge_procedure | MEASURED |
| Amendment fields left unchanged | ["outcome", "baseline", "effect", "interval", "bootstrap", "frozen_thresholds"] | config/residual_prereg.yaml amendments.0.unchanged | MEASURED |
| Refusal count in the amendment happened on the three takes | not in a committed fusion file | README.md:180 and the amendment reason. Check: open gitignored fusion.json for take_0525, take_0526, and take_0527 and count guard refusals. artifacts/runs was absent in this worktree on 2026-10-07. | NOT VERIFIED |

## Results on the two stock plumbing clips

The only committed take records are `reports/pexels_5510095.take.json` and `reports/pexels_5510143.take.json`. Both are labeled `PLUMBING TEST`. Both have `visual_judge.status` `blocked_before_job_create`, empty verdicts, `fusion.status` `not_run_missing_visual_verdicts`, and `cleanup.nebius_jobs_started` 0. Nebius GPU cost and Token Factory cost on these records are 0. There is no Cosmos agreement and no fusion decision for either clip, because those stages did not run.

`artifacts/` is gitignored and was not present in this worktree. The numbers below are the committed take records, not a re-run of GEM-X or the simulator.

### pexels_5510095

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| Short clip label | "PLUMBING TEST" | reports/pexels_5510095.take.json label | MEASURED |
| Short clip source frames | 222 | reports/pexels_5510095.take.json source.frames | MEASURED |
| Short clip source fps | 25.0 | reports/pexels_5510095.take.json source.fps | MEASURED |
| Short clip pose duration in seconds | 8.84 | reports/pexels_5510095.take.json source.pose_duration_s | MEASURED |
| Short clip run id | "pexels_5510095-20261005-ff05d94-r1" | reports/pexels_5510095.take.json replay_validation.run_id | MEASURED |
| Short clip clean Showhand commit | "ff05d94053023bce7d5b4dc17d6ad581ba4c1604" | reports/pexels_5510095.take.json code_commit_sha | MEASURED |
| Short clip tree clean at replay | true | reports/pexels_5510095.take.json code_tree_clean | MEASURED |
| Short clip SOMA to SMPL precompute seconds | 6.672333780996269 | reports/pexels_5510095.take.json timings_s.soma_to_smpl_precompute | MEASURED |
| Short clip 50 Hz replay seconds | 8.840000754 | reports/pexels_5510095.take.json timings_s.sonic_replay_50_hz | MEASURED |
| Short clip max publish jitter seconds | 0.005299424003169406 | reports/pexels_5510095.take.json replay_validation.publish_jitter_max_s | MEASURED |
| Short clip allowed jitter seconds | 0.01 | reports/pexels_5510095.take.json replay_validation.max_allowed_jitter_s | MEASURED |
| Short clip publisher warmup seconds | 0.5 | reports/pexels_5510095.take.json replay_validation.publisher_warmup_s | MEASURED |
| Short clip SONIC frames received | 443 | reports/pexels_5510095.take.json replay_validation.sonic_received_frames | MEASURED |
| Short clip SONIC first frame | 0 | reports/pexels_5510095.take.json replay_validation.sonic_first_frame | MEASURED |
| Short clip SONIC final frame | 442 | reports/pexels_5510095.take.json replay_validation.sonic_final_frame | MEASURED |
| Short clip post-roll evaluated seconds | 0.60587 | reports/pexels_5510095.take.json replay_validation.post_roll_evaluated_s | MEASURED |
| Short clip offline render seconds | 130.99 | reports/pexels_5510095.take.json timings_s.offline_sim_render | MEASURED |
| Short clip paired-frame seconds | 2.610044 | reports/pexels_5510095.take.json timings_s.visual_pair_extraction | MEASURED |
| Short clip metrics seconds | 0.919013 | reports/pexels_5510095.take.json timings_s.deterministic_metrics | MEASURED |
| Short clip GEM-X and retarget total seconds | 523.342527984 | reports/pexels_5510095.take.json timings_s.gem_x_and_retarget_total | MEASURED |
| Short clip pose and failed retarget seconds | 290.748189425 | reports/pexels_5510095.take.json timings_s.gem_x_pose_and_failed_retarget | MEASURED |
| Short clip saved-result retarget seconds | 232.594338559 | reports/pexels_5510095.take.json timings_s.saved_result_newton_retarget | MEASURED |
| Short clip Cosmos job seconds | 0.0 | reports/pexels_5510095.take.json timings_s.cosmos_job | MEASURED |
| Short clip Nemotron fusion seconds | 0.0 | reports/pexels_5510095.take.json timings_s.nemotron_fusion | MEASURED |
| Short clip tracking mean absolute error radians | 0.529236 | reports/pexels_5510095.take.json metrics.tracking_mean_abs_error_rad | MEASURED |
| Short clip tracking p95 absolute error radians | 1.272042 | reports/pexels_5510095.take.json metrics.tracking_p95_abs_error_rad | MEASURED |
| Short clip minimum root height meters | 0.189993 | reports/pexels_5510095.take.json metrics.root_height_min_m | MEASURED |
| Short clip maximum root tilt degrees | 85.342885 | reports/pexels_5510095.take.json metrics.root_tilt_max_deg | MEASURED |
| Short clip maximum contact-foot slip meters per second | 0.989901 | reports/pexels_5510095.take.json metrics.foot_slip_max_m_s | MEASURED |
| Short clip contact-foot slip seconds | 1.372307 | reports/pexels_5510095.take.json metrics.foot_slip_seconds | MEASURED |
| Short clip time out of balance seconds | 5.984513 | reports/pexels_5510095.take.json metrics.out_of_balance_seconds | MEASURED |
| Short clip falls | 7 | reports/pexels_5510095.take.json metrics.falls | MEASURED |
| Short clip deterministic pass | false | reports/pexels_5510095.take.json metrics.pass | MEASURED |
| Short clip reason codes | ["tracking_mean_abs_error_rad", "tracking_p95_abs_error_rad", "root_height_m", "root_tilt_deg", "foot_slip", "out_of_balance", "fall"] | reports/pexels_5510095.take.json metrics.reason_codes | MEASURED |
| Short clip visual model id on the blocked record | "nvidia/Cosmos-Reason1-7B" | reports/pexels_5510095.take.json visual_judge.model_id | MEASURED |
| Short clip visual status | "blocked_before_job_create" | reports/pexels_5510095.take.json visual_judge.status | MEASURED |
| Short clip fusion model id on the unrun record | "nvidia/Nemotron-3_5-Lightning" | reports/pexels_5510095.take.json fusion.model_id | MEASURED |
| Short clip fusion status | "not_run_missing_visual_verdicts" | reports/pexels_5510095.take.json fusion.status | MEASURED |
| Short clip Nebius jobs started | 0 | reports/pexels_5510095.take.json cleanup.nebius_jobs_started | MEASURED |
| Short clip Nebius GPU cost USD | 0.0 | reports/pexels_5510095.take.json cost_usd.nebius_gpu | MEASURED |
| Short clip Token Factory cost USD | 0.0 | reports/pexels_5510095.take.json cost_usd.token_factory | MEASURED |
| Short clip total cost USD | 0.0 | reports/pexels_5510095.take.json cost_usd.total | MEASURED |
| Short clip threshold commit stored on the record | "0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9" | reports/pexels_5510095.take.json threshold_commit_sha | MEASURED |
| Short clip threshold sha256 stored on the record | "206c194a8863e9a7aa2ac2c9bb88edff10271aad224d34194fad215fe2076b76" | reports/pexels_5510095.take.json threshold_sha256 | MEASURED |
| Short clip missing sam_3d_body error | "ModuleNotFoundError: No module named 'sam_3d_body'" | reports/pexels_5510095.take.json errors.0 | MEASURED |
| Short clip retarget conversion error | "ValueError: could not convert string to float: 'size'" | reports/pexels_5510095.take.json errors.1 | MEASURED |
| Short clip injected-archive limit error | "Nebius injected archive was 290162 bytes and exceeded the 65536 byte limit" | reports/pexels_5510095.take.json errors.2 | MEASURED |
| Short clip visual-job auth error | "Nebius CLI browser authorization timed out before job creation: context deadline exceeded; trace ID d87414b7bf30576eb3a7b62a45f0fc39" | reports/pexels_5510095.take.json errors.6 | MEASURED |

The README's `86.663354` second duration for the `sam_3d_body` failure is not in this record. The error string is. The duration is NOT VERIFIED. Check: find the log line that pairs that exception with `86.663354`. `git grep 86.663354 HEAD` hits only `README.md:130`.

### pexels_5510143

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| Long clip label | "PLUMBING TEST" | reports/pexels_5510143.take.json label | MEASURED |
| Long clip source frames | 441 | reports/pexels_5510143.take.json source.frames | MEASURED |
| Long clip source fps | 25.0 | reports/pexels_5510143.take.json source.fps | MEASURED |
| Long clip pose duration in seconds | 17.6 | reports/pexels_5510143.take.json source.pose_duration_s | MEASURED |
| Long clip run id | "pexels_5510143-20261005-ff05d94-r1" | reports/pexels_5510143.take.json replay_validation.run_id | MEASURED |
| Long clip clean Showhand commit | "ff05d94053023bce7d5b4dc17d6ad581ba4c1604" | reports/pexels_5510143.take.json code_commit_sha | MEASURED |
| Long clip tree clean at replay | true | reports/pexels_5510143.take.json code_tree_clean | MEASURED |
| Long clip SOMA to SMPL precompute seconds | 10.174045968997234 | reports/pexels_5510143.take.json timings_s.soma_to_smpl_precompute | MEASURED |
| Long clip 50 Hz replay seconds | 17.600001754 | reports/pexels_5510143.take.json timings_s.sonic_replay_50_hz | MEASURED |
| Long clip max publish jitter seconds | 0.001185463996080216 | reports/pexels_5510143.take.json replay_validation.publish_jitter_max_s | MEASURED |
| Long clip allowed jitter seconds | 0.01 | reports/pexels_5510143.take.json replay_validation.max_allowed_jitter_s | MEASURED |
| Long clip publisher warmup seconds | 0.5 | reports/pexels_5510143.take.json replay_validation.publisher_warmup_s | MEASURED |
| Long clip SONIC frames received | 881 | reports/pexels_5510143.take.json replay_validation.sonic_received_frames | MEASURED |
| Long clip SONIC first frame | 0 | reports/pexels_5510143.take.json replay_validation.sonic_first_frame | MEASURED |
| Long clip SONIC final frame | 880 | reports/pexels_5510143.take.json replay_validation.sonic_final_frame | MEASURED |
| Long clip post-roll evaluated seconds | 0.605106 | reports/pexels_5510143.take.json replay_validation.post_roll_evaluated_s | MEASURED |
| Long clip offline render seconds | 234.79 | reports/pexels_5510143.take.json timings_s.offline_sim_render | MEASURED |
| Long clip paired-frame seconds | 4.074039 | reports/pexels_5510143.take.json timings_s.visual_pair_extraction | MEASURED |
| Long clip metrics seconds | 1.023692 | reports/pexels_5510143.take.json timings_s.deterministic_metrics | MEASURED |
| Long clip GEM-X and Newton retarget seconds | 722.984161058 | reports/pexels_5510143.take.json timings_s.gem_x_and_newton_retarget | MEASURED |
| Long clip Cosmos job seconds | 0.0 | reports/pexels_5510143.take.json timings_s.cosmos_job | MEASURED |
| Long clip Nemotron fusion seconds | 0.0 | reports/pexels_5510143.take.json timings_s.nemotron_fusion | MEASURED |
| Long clip tracking mean absolute error radians | 0.485284 | reports/pexels_5510143.take.json metrics.tracking_mean_abs_error_rad | MEASURED |
| Long clip tracking p95 absolute error radians | 1.119977 | reports/pexels_5510143.take.json metrics.tracking_p95_abs_error_rad | MEASURED |
| Long clip minimum root height meters | 0.189966 | reports/pexels_5510143.take.json metrics.root_height_min_m | MEASURED |
| Long clip maximum root tilt degrees | 85.422806 | reports/pexels_5510143.take.json metrics.root_tilt_max_deg | MEASURED |
| Long clip maximum contact-foot slip meters per second | 0.989901 | reports/pexels_5510143.take.json metrics.foot_slip_max_m_s | MEASURED |
| Long clip contact-foot slip seconds | 2.757829 | reports/pexels_5510143.take.json metrics.foot_slip_seconds | MEASURED |
| Long clip time out of balance seconds | 11.291179 | reports/pexels_5510143.take.json metrics.out_of_balance_seconds | MEASURED |
| Long clip falls | 14 | reports/pexels_5510143.take.json metrics.falls | MEASURED |
| Long clip deterministic pass | false | reports/pexels_5510143.take.json metrics.pass | MEASURED |
| Long clip reason codes | ["tracking_p95_abs_error_rad", "root_height_m", "root_tilt_deg", "foot_slip", "out_of_balance", "fall"] | reports/pexels_5510143.take.json metrics.reason_codes | MEASURED |
| Long clip visual model id on the blocked record | "nvidia/Cosmos-Reason1-7B" | reports/pexels_5510143.take.json visual_judge.model_id | MEASURED |
| Long clip visual status | "blocked_before_job_create" | reports/pexels_5510143.take.json visual_judge.status | MEASURED |
| Long clip fusion model id on the unrun record | "nvidia/Nemotron-3_5-Lightning" | reports/pexels_5510143.take.json fusion.model_id | MEASURED |
| Long clip fusion status | "not_run_missing_visual_verdicts" | reports/pexels_5510143.take.json fusion.status | MEASURED |
| Long clip Nebius jobs started | 0 | reports/pexels_5510143.take.json cleanup.nebius_jobs_started | MEASURED |
| Long clip Nebius GPU cost USD | 0.0 | reports/pexels_5510143.take.json cost_usd.nebius_gpu | MEASURED |
| Long clip Token Factory cost USD | 0.0 | reports/pexels_5510143.take.json cost_usd.token_factory | MEASURED |
| Long clip total cost USD | 0.0 | reports/pexels_5510143.take.json cost_usd.total | MEASURED |
| Long clip first GEM-X kill error | "Linux Killed the first GEM-X attempt under the image-feature path" | reports/pexels_5510143.take.json errors.0 | MEASURED |
| Long clip jitter failure at frame 710 | "RuntimeError: 50 Hz publish jitter 0.032240s exceeds 0.010000s at frame 710" | reports/pexels_5510143.take.json errors.2 | MEASURED |
| Long clip jitter failure at frame 333 | "RuntimeError: 50 Hz publish jitter 0.142612s exceeds 0.010000s at frame 333" | reports/pexels_5510143.take.json errors.3 | MEASURED |
| Long clip jitter failure at frame 18 | "RuntimeError: 50 Hz publish jitter 0.044585s exceeds 0.010000s at frame 18" | reports/pexels_5510143.take.json errors.5 | MEASURED |
| Long clip telemetry gap error | "showhand.metrics.MetricsInputError: telemetry gap 0.342198s exceeds 0.050000s" | reports/pexels_5510143.take.json errors.6 | MEASURED |
| Long clip jitter failure at frame 199 | "RuntimeError: 50 Hz publish jitter 0.010615s exceeds 0.010000s at frame 199" | reports/pexels_5510143.take.json errors.7 | MEASURED |
| Long clip withdrawn SONIC receipt error | "A replay later withdrawn from grading had SONIC receipt frames 5 through 880, not the required 0 through 880" | reports/pexels_5510143.take.json errors.8 | MEASURED |
| Long clip visual-job auth error | "Nebius CLI browser authorization timed out before job creation: context deadline exceeded; trace ID d87414b7bf30576eb3a7b62a45f0fc39" | reports/pexels_5510143.take.json errors.9 | MEASURED |

Both records fail tracking p95, root height, root tilt, foot slip, time out of balance, and fall. The short record also fails tracking mean. The long record's reason codes do not include tracking mean. That matches the README sentence at `README.md:126`. The stored metric numbers above are the exact JSON values. Several README cells round them. See [Drift found](#drift-found).

## Results on Stephen's three takes

Stephen's takes are not in a committed take record. `git grep` for `take_0525`, `take0525`, and `aijob-` hits only `README.md`. `artifacts/` and `artifacts/runs/` were absent in this worktree on 2026-10-07. Per-take `visual.json` and `fusion.json` are gitignored. The README records job ids next to the visual and fusion figures. That does not put the figures in the repo. Every value in this section is NOT VERIFIED. Do not narrate them as measured.

The check for each row is the same: open the gitignored take record, `metrics.json`, `visual.json`, and `fusion.json` for that take and compare the field to the README. The README says at line 194 that those take records still list the visual judge as blocked and have not been regenerated with the job ids. That sentence is also unverified, because the records are not committed.

`git rev-parse c6847f2` printed `c6847f2738f00fcea61dcf107325d6907034e28b`. `git rev-parse c82fdba` printed `c82fdbaaad4f7f9a11db9e097b8e2fad477d8bf1`. Those commits exist. That does not show that a replay started from a clean tree at either commit.

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| take_0525 source frames at 30 fps | 184 | README.md:142. Check the gitignored take record. | NOT VERIFIED |
| take_0526 source frames at 30 fps | 187 | README.md:142. Check the gitignored take record. | NOT VERIFIED |
| take_0527 source frames at 30 fps | 178 | README.md:142. Check the gitignored take record. | NOT VERIFIED |
| take_0525 target motion duration | 6.1 s | README.md:143. Check the gitignored take record. | NOT VERIFIED |
| take_0526 target motion duration | 6.2 s | README.md:143. Check the gitignored take record. | NOT VERIFIED |
| take_0527 target motion duration | 5.9 s | README.md:143. Check the gitignored take record. | NOT VERIFIED |
| take_0525 run id | take0525-20261005-c6847f2-r1 | README.md:144. Check the gitignored take record. | NOT VERIFIED |
| take_0526 run id | take0526-20261005-c82fdba-r1 | README.md:144. Check the gitignored take record. | NOT VERIFIED |
| take_0527 run id | take0527-20261005-c82fdba-r1 | README.md:144. Check the gitignored take record. | NOT VERIFIED |
| take_0525 frames published | 306 | README.md:146. Check the gitignored take record. | NOT VERIFIED |
| take_0526 frames published | 311 | README.md:146. Check the gitignored take record. | NOT VERIFIED |
| take_0527 frames published | 296 | README.md:146. Check the gitignored take record. | NOT VERIFIED |
| take_0525 max publish jitter | 0.000039 s | README.md:147. Check the gitignored take record. | NOT VERIFIED |
| take_0526 max publish jitter | 0.000086 s | README.md:147. Check the gitignored take record. | NOT VERIFIED |
| take_0527 max publish jitter | 0.000103 s | README.md:147. Check the gitignored take record. | NOT VERIFIED |
| take_0525 publish deadline misses | 0 | README.md:148. Check the gitignored take record. | NOT VERIFIED |
| take_0526 publish deadline misses | 0 | README.md:148. Check the gitignored take record. | NOT VERIFIED |
| take_0527 publish deadline misses | 0 | README.md:148. Check the gitignored take record. | NOT VERIFIED |
| take_0525 tracking mean absolute error | 0.240200 rad | README.md:149. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 tracking mean absolute error | 0.221003 rad | README.md:149. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 tracking mean absolute error | 0.232949 rad | README.md:149. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 tracking p95 absolute error | 0.695321 rad | README.md:150. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 tracking p95 absolute error | 0.603113 rad | README.md:150. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 tracking p95 absolute error | 0.716256 rad | README.md:150. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 minimum root height | 0.473044 m | README.md:151. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 minimum root height | 0.756251 m | README.md:151. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 minimum root height | 0.481920 m | README.md:151. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 maximum root tilt | 23.134581 degrees | README.md:152. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 maximum root tilt | 7.273088 degrees | README.md:152. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 maximum root tilt | 23.326847 degrees | README.md:152. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 maximum contact-foot slip | 1.486444 m/s | README.md:153. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 maximum contact-foot slip | 1.546044 m/s | README.md:153. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 maximum contact-foot slip | 0.979841 m/s | README.md:153. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 contact-foot slip time | 0.784643 s | README.md:154. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 contact-foot slip time | 0.365411 s | README.md:154. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 contact-foot slip time | 0.489463 s | README.md:154. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 time out of balance | 1.275880 s | README.md:155. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 time out of balance | 0.552972 s | README.md:155. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 time out of balance | 0.526571 s | README.md:155. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 falls | 0 | README.md:156. Check the gitignored metrics. | NOT VERIFIED |
| take_0526 falls | 0 | README.md:156. Check the gitignored metrics. | NOT VERIFIED |
| take_0527 falls | 0 | README.md:156. Check the gitignored metrics. | NOT VERIFIED |
| take_0525 deterministic result | fail: foot slip, out of balance | README.md:157. Check the gitignored metrics reason codes. | NOT VERIFIED |
| take_0526 deterministic result | fail: out of balance | README.md:157. Check the gitignored metrics reason codes. | NOT VERIFIED |
| take_0527 deterministic result | fail: out of balance | README.md:157. Check the gitignored metrics reason codes. | NOT VERIFIED |
| take_0525 seconds that fail on their own | 1 to 2 (tracking p95) | README.md:158. Check the gitignored per-second metrics. | NOT VERIFIED |
| take_0526 seconds that fail on their own | 0 to 1 (out of balance), 2 to 3 (tracking p95) | README.md:158. Check the gitignored per-second metrics. | NOT VERIFIED |
| take_0527 seconds that fail on their own | none | README.md:158. Check the gitignored per-second metrics. | NOT VERIFIED |
| take_0525 Cosmos windows that match | 6 of 7 | README.md:170. Job id in README.md:172 is aijob-e00d1f0neh67r4nnrt. Check gitignored visual.json for that job. | NOT VERIFIED |
| take_0526 Cosmos windows that match | 7 of 7 | README.md:170. Job id in README.md:172 is aijob-e00dpjhqxkn5xgvb76. Check gitignored visual.json for that job. | NOT VERIFIED |
| take_0527 Cosmos windows that match | 5 of 6 | README.md:170. Job id in README.md:172 is aijob-e00xc8v043dvrrdgn5. Check gitignored visual.json for that job. | NOT VERIFIED |
| take_0525 Cosmos mismatch | 4 to 5 s: upper body, lower body, orientation | README.md:171. Check gitignored visual.json for aijob-e00d1f0neh67r4nnrt. | NOT VERIFIED |
| take_0526 Cosmos mismatch | none | README.md:171. Check gitignored visual.json for aijob-e00dpjhqxkn5xgvb76. | NOT VERIFIED |
| take_0527 Cosmos mismatch | 3 to 4 s: upper body, lower body, orientation | README.md:171. Check gitignored visual.json for aijob-e00xc8v043dvrrdgn5. | NOT VERIFIED |
| take_0525 fusion status in the README | deterministic fallback after 2 guard refusals | README.md:173. Check gitignored fusion.json. | NOT VERIFIED |
| take_0526 fusion status in the README | passed after one retry | README.md:173. Check gitignored fusion.json. | NOT VERIFIED |
| take_0527 fusion status in the README | passed after one retry | README.md:173. Check gitignored fusion.json. | NOT VERIFIED |
| take_0525 fused decision in the README | re-show 1 to 2 s and 4 to 5 s | README.md:174. Check gitignored fusion.json. | NOT VERIFIED |
| take_0526 fused decision in the README | re-show 0 to 1 s | README.md:174. Check gitignored fusion.json. | NOT VERIFIED |
| take_0527 fused decision in the README | re-show 3 to 4 s | README.md:174. Check gitignored fusion.json. | NOT VERIFIED |
| take_0525 Token Factory request ids in the README | 5f8b02c559b5532e97fc393dd83d92cd and 55e67f4ad5ca373c73f65c11b0934400 | README.md:175. Check gitignored fusion.json. | NOT VERIFIED |
| take_0526 Token Factory request ids in the README | ef1546107a4724d7d1585335e2afb568 and 639193fa38ca5f6abc8e276b697ab41d | README.md:175. Check gitignored fusion.json. | NOT VERIFIED |
| take_0527 Token Factory request ids in the README | 17e8b467742ee10f7a3e250ebf86cd73 and a455ed7681a48218f6ab822aa9aa8e9e | README.md:175. Check gitignored fusion.json. | NOT VERIFIED |
| take_0525 fusion cost in the README | 0.00030144 USD | README.md:176. Check gitignored fusion.json usage and cost. | NOT VERIFIED |
| take_0526 fusion cost in the README | 0.00028386 USD | README.md:176. Check gitignored fusion.json usage and cost. | NOT VERIFIED |
| take_0527 fusion cost in the README | 0.00028020 USD | README.md:176. Check gitignored fusion.json usage and cost. | NOT VERIFIED |
| Cosmos load, window, and job wall times in the README | load 282 to 283 s, windows 1.2 to 3.5 s, walls 315 s, 313 s, and 312 s, 940 s in all | README.md:166. Check gitignored visual.json model_load_s, verdict latency_s, and the Nebius job record for the three job ids. | NOT VERIFIED |
| L40S price estimate in the README | about 0.38 USD from 1.35 USD per GPU hour plus 0.012 USD per vCPU hour and 8 vCPUs | README.md:166. The README says this is a price-list estimate, not a billing reading. No price URL or invoice is in the repo. Check the Nebius price page and the billing record for the three job ids. | NOT VERIFIED |
| Earlier take_0525 fusion request in the README | request 503cf0e1add30b7ca120deaabebf59ca passed on the first answer with re-show 1 to 2 s | README.md:180. Check the saved raw response for that request id. | NOT VERIFIED |
| Phone recording claim | IMG_0525 to IMG_0527 at 30 fps on 2026-10-05 | README.md:138. Check the gitignored source videos and their container metadata. | NOT VERIFIED |

## Models and services

Pinned ids and request settings below are what the code sends. They are not proof that a job finished, except where a take record says so. The plumbing records say the visual job was blocked before creation.

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| Cosmos model id in the visual judge | "nvidia/Cosmos-Reason1-7B" | tools/cosmos_job/visual_judge.py:17 | MEASURED |
| Cosmos revision pin | "375e24000b24baed78f4618d3dd779e47cd96323" | tools/cosmos_job/visual_judge.py:18 | MEASURED |
| Cosmos container image digest pin | "sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be" | tools/cosmos_job/visual_judge.py:19 | MEASURED |
| Cosmos torch dtype in the judge | bfloat16 | tools/cosmos_job/visual_judge.py:84 | MEASURED |
| Cosmos decoding | do_sample false, max_new_tokens default 4096 | tools/cosmos_job/visual_judge.py:70 and tools/cosmos_job/visual_judge.py:125 | MEASURED |
| Job image | pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime at the digest above | tools/cosmos_job/submit.sh:13 | MEASURED |
| Nebius CLI profile | hackathon | tools/cosmos_job/submit.sh:41 | MEASURED |
| Nebius parent id | project-e00mwywjpr00x87mxbjn98 | tools/cosmos_job/submit.sh:44 | MEASURED |
| Nebius platform | gpu-l40s-a | tools/cosmos_job/submit.sh:45 | MEASURED |
| Nebius preset | 1gpu-8vcpu-32gb | tools/cosmos_job/submit.sh:46 | MEASURED |
| Nebius job timeout | 45m | tools/cosmos_job/submit.sh:47 | MEASURED |
| Nebius disk size | 100Gi | tools/cosmos_job/submit.sh:48 | MEASURED |
| Injected-file refusal limit in submit.sh | 65536 bytes | tools/cosmos_job/submit.sh:35 | MEASURED |
| Bucket mount when PAIRS_BUCKET is set | read-only volume at /data | tools/cosmos_job/submit.sh:19 | MEASURED |
| Packages installed inside the job | transformers 5.6.1, accelerate 1.12.0, qwen-vl-utils 0.0.14, pillow 12.3.0, torchvision 0.26.0, av 16.1.0 | tools/cosmos_job/run.sh:13 to tools/cosmos_job/run.sh:15 | MEASURED |
| Log fetch | ai logs with --since 168h and --tail 1000, then the delimited gzip payload | tools/cosmos_job/fetch.sh:19 and tools/cosmos_job/fetch.sh:23 | MEASURED |
| Accepted job state | COMPLETED only | tools/cosmos_job/validate_result.py:32 | MEASURED |
| Nemotron model id | "nvidia/Nemotron-3_5-Lightning" | src/showhand/fusion.py:15 | MEASURED |
| Token Factory base URL | "https://api.tokenfactory.nebius.com/v1/chat/completions" | src/showhand/fusion.py:16 | MEASURED |
| Fusion temperature | 0 | src/showhand/fusion.py:72 | MEASURED |
| Fusion max tokens | 1200 | src/showhand/fusion.py:73 | MEASURED |
| Fusion JSON schema strict flag | true | src/showhand/fusion.py:80 | MEASURED |
| Fusion enable_thinking | false | src/showhand/fusion.py:83 | MEASURED |
| Fusion attempts before deterministic fallback | 2 | src/showhand/fusion.py:21 | MEASURED |
| Token cost constants in code | 0.06 USD per million input tokens and 0.24 USD per million output tokens | src/showhand/fusion.py:17 and src/showhand/fusion.py:18 | MEASURED |
| GEM-X model string printed by the offline driver | nvidia/GEM-X | tools/wsl/run_gemx_offline.sh:24 | MEASURED |
| GEM-X demo invocation | scripts/demo/demo_soma_onnx.py with --no-imgfeat and --retarget | tools/wsl/run_gemx_offline.sh:30 to tools/wsl/run_gemx_offline.sh:34 | MEASURED |
| Replay output fps default | 50 | tools/wsl/replay_soma_v3.py:52 | MEASURED |
| Replay max jitter default seconds | 0.01 | tools/wsl/replay_soma_v3.py:58 | MEASURED |
| Replay post-roll default seconds | 0.6 | tools/wsl/replay_soma_v3.py:59 | MEASURED |
| Replay publisher warmup default seconds | 0.5 | tools/wsl/replay_soma_v3.py:60 | MEASURED |
| Replay final pacing margin seconds | 0.003 | tools/wsl/replay_soma_v3.py:19 | MEASURED |
| Take driver passes the same replay gates | output fps 50, max jitter 0.01, post-roll 0.6, warmup 0.5 | tools/wsl/run_take.sh:483 to tools/wsl/run_take.sh:489 | MEASURED |
| Hugging Face model card claims in the README | license, image and video input, BF16 tests, H100, A100, and GB200 hardware | README.md:28 cites https://huggingface.co/nvidia/Cosmos-Reason1-7B. This sheet did not open that URL. | NOT VERIFIED |
| NIM 24 GB BF16 requirement in the README | 24 GB for the 7B model | README.md:28 cites https://docs.nvidia.com/nim/vision-language-models/latest/support-matrix.html. This sheet did not open that URL. | NOT VERIFIED |
| Nebius sentence that COMPLETED means success | the comment quotes docs.nebius.com | tools/cosmos_job/validate_result.py:30 cites https://docs.nebius.com/serverless/lifecycle#job-statuses. This sheet did not open that URL. The code's accepted state is MEASURED above. | NOT VERIFIED |

The guard in `src/showhand/guard.py` rejects a fusion object whose keys are not the strict set, an accept that cites negative evidence or contradicts a failing overall metric or a visual mismatch, a window outside the take or not exactly equal to cited negative evidence, and reason text that is not exactly `<reason_code> in cited evidence` for a code on that cited evidence. Those rules are the function `guard_fusion` at `src/showhand/guard.py:40`.

## Tests and CI

`.github/workflows/ci.yml` defines one job. Its name is `test`. It runs on `ubuntu-24.04`, checks out with `fetch-depth: 0`, sets up Python `3.12`, installs `.[dev]`, then runs three gates: `python -m ruff format --check .`, `python -m ruff check .`, and `python -m pytest`.

Those three gates were run locally on 2026-10-07 against commit `4913ad4e04e020a94fce724705e67eae70ccde1b` before this file and before `tests/test_facts.py`. `uv run --offline --extra dev` could not resolve numpy from the uv cache, and no package was downloaded. The interpreter was Windows CPython 3.12.10 from `C:\dev\Nebius-NVIDIA-Global-AI\showhand\app\.venv` (ruff 0.16.10, pytest 9.1.1). That checkout is `main` at the same SHA, and `src/showhand/fusion.py` is blob `d4a4140068a7f0124970e0b91ed738cb89df80dd` in both checkouts. The working directory was this worktree.

| Claim | Value | Source | Tag |
| --- | --- | --- | --- |
| CI job name | test | .github/workflows/ci.yml:8 | MEASURED |
| CI runner image | ubuntu-24.04 | .github/workflows/ci.yml:9 | MEASURED |
| CI Python version | 3.12 | .github/workflows/ci.yml:17 | MEASURED |
| ruff format --check exit code | 0 | command: python -m ruff format --check . on 4913ad4. Output: 29 files already formatted | MEASURED |
| ruff check exit code | 0 | command: python -m ruff check . on 4913ad4. Output: All checks passed! | MEASURED |
| pytest exit code | 0 | command: python -m pytest on 4913ad4. Output: 61 passed in 3.23s | MEASURED |
| pytest count at that commit | 61 | command: python -m pytest on 4913ad4. This count does not include tests/test_facts.py | MEASURED |

The hosted GitHub Actions run for this SHA was not queried.

## Do not claim

- Do not claim an outside person has graded a take. No committed human labels exist. The pre-registration status is still waiting.
- Do not claim the visual judge or the fused decision agrees with a human grader. That comparison has no result.
- Do not claim a real Unitree robot ran. The path in this repo is a MuJoCo simulation.
- Do not claim product results beyond the two committed Pexels plumbing records. Stephen's three takes are README text until their gitignored artifacts are opened.
- Do not claim Cosmos or Nemotron graded the two Pexels clips. Both records are blocked before job creation. GPU time and GPU cost on those records are zero.
- Do not claim the README's Cosmos match counts, fusion decisions, request ids, job wall times, or fusion dollar amounts for Stephen's takes. They are NOT VERIFIED.
- Do not claim the about 0.38 USD figure is a bill. The README calls it a price-list estimate, and the price list is not in the repo.
- Do not claim Nemotron at temperature 0 is deterministic. The README says an earlier answer differed, and that run is NOT VERIFIED here. The code still sends temperature 0.
- Do not claim Stephen's committed take records contain the Nebius job ids. No such records are committed. The README says the records still list the visual judge as blocked.
- Do not claim the exact GEM-X or GEAR-SONIC checkout, weights, or planner that produced the plumbing runs. The README says those runtime commits were not captured. The take records hash saved outputs. They do not name those external commits.
- Do not claim the model card's license, hardware list, or 24 GB BF16 figure. Those pages were not opened.
- Do not claim the job preset is a 48 GB GPU. `submit.sh` asks for platform `gpu-l40s-a` and preset `1gpu-8vcpu-32gb`.
- Do not claim `NewtonPipeline(skeleton, "soma", "unitree_g1")` is a call site in this repo. It is a README sentence. This repo calls `run_retarget`.
- Do not claim the synthetic residual unit-test rows are a result. The pre-registration forbids that.
- Do not claim MuJoCo or SONIC repeats the same trajectory on a later launch. The README already refuses that claim, and nothing here re-ran the simulator.

## Drift found

The committed file wins. The README cell is the rounded or paraphrased form.

1. `README.md:105` prints `523.342528` s for `pexels_5510095` GEM-X and retarget. `timings_s.gem_x_and_retarget_total` is `523.342527984`.
2. `README.md:108` prints `6.672334` s for the short clip SOMA conversion. `timings_s.soma_to_smpl_precompute` is `6.672333780996269`.
3. `README.md:109` prints `8.840001` s for the short clip replay. `timings_s.sonic_replay_50_hz` is `8.840000754`.
4. `README.md:130` prints `232.594339` s for the saved-result retarget. `timings_s.saved_result_newton_retarget` is `232.594338559`.
5. `README.md:108` prints `10.174046` s for the long clip SOMA conversion. `timings_s.soma_to_smpl_precompute` is `10.174045968997234`.
6. `README.md:109` prints `17.600002` s for the long clip replay. `timings_s.sonic_replay_50_hz` is `17.600001754`.
7. `README.md:95` says one take's pairs are about 300 KB. The short clip `errors.2` says the injected archive was `290162` bytes and exceeded `65536`.
8. `README.md:130` gives `86.663354` seconds for the `sam_3d_body` failure. That duration is not in the take record. Only the exception string is.
9. `README.md:28` says a 48 GB L40S. `tools/cosmos_job/submit.sh:46` sets preset `1gpu-8vcpu-32gb`. The 48 GB figure is not in the job file.
10. `README.md:12` names `NewtonPipeline(skeleton, "soma", "unitree_g1")`. No file in this repo contains that call. `tools/wsl/finish_gemx_retarget.py:27` calls `run_retarget`.
11. Stephen's metric table (`README.md:140` to `README.md:176`), the job ids, and the fusion costs have no committed JSON. They are not confirmed and they are not contradicted by a committed file. They stay NOT VERIFIED.
12. The amendment date `2026-10-06` and commit `9fb9c782af1010a6c414c534386d19fa7e4d226d` at `2026-10-05 23:55:50 -0400` are the same instant in UTC (`2026-10-06 03:55:50`). The local calendar date and the yaml date are not the same label.

README cells that round to six decimal places and match the stored value at those places are not listed. That includes short-clip jitter `0.005299`, long-clip jitter `0.001185`, the failed-retarget `290.748189`, and the long-clip GEM-X total `722.984161`. Short-clip post-roll `0.605870` is the same number as stored `0.60587`.
