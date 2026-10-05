#!/usr/bin/env bash
# Run one local Showhand take and stop every process this script starts.
# Usage: run_take.sh TAKE_VIDEO OUTPUT_ROOT RUN_ID
# OUTPUT_ROOT must be a new gitignored directory inside this repository.
# Thresholds, jitter, drain, and the support-band release are unchanged.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: run_take.sh TAKE_VIDEO OUTPUT_ROOT RUN_ID" >&2
  exit 2
fi

take_video=$1
output_root=$2
run_id=$3
repo=$(cd "$(dirname "$0")/../.." && pwd)
gemx_root=/home/stephensookra/showhand/GEM-X
sonic_root=/home/stephensookra/showhand/GR00T-WholeBodyControl
frozen_threshold_commit=0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9

sim_pid=""
sonic_pid=""
replay_pid=""
gemx_pid=""
render_pid=""
current_log=""
signaled_sim=0
signaled_sonic=0

die() {
  echo "SHOWHAND_DRIVER_FAIL: $*" >&2
  if [ -n "$current_log" ] && [ -f "$current_log" ]; then
    echo "--- tail $current_log ---" >&2
    tail -n 40 "$current_log" >&2 || true
  fi
  exit 1
}

append_timing() {
  printf '%s\t%s\n' "$1" "$2" >> "$output_root/driver/timing.tsv"
}

elapsed_s() {
  python3 -c 'import sys; print((int(sys.argv[2]) - int(sys.argv[1])) / 1e9)' "$1" "$2"
}

write_timings() {
  [ -d "$output_root/driver" ] || return 0
  python3 - "$output_root/driver/timing.tsv" "$output_root/driver/stage_timings.json" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
data = {}
if source.is_file():
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        key, value = line.split("\t", 1)
        data[key] = float(value)
target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

kill_group() {
  local pid=$1
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM -"$pid" 2>/dev/null || true
    return 0
  fi
  return 1
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  local alive=0
  local pid
  for pid in "$replay_pid" "$sonic_pid" "$sim_pid" "$gemx_pid" "$render_pid"; do
    if kill_group "$pid"; then
      alive=1
    fi
  done
  if [ -n "${output_root:-}" ] && [ -f "$output_root/driver/sonic-status/sonic_pid" ]; then
    local sonic_child
    sonic_child=$(tr -d '[:space:]' < "$output_root/driver/sonic-status/sonic_pid")
    if kill_group "$sonic_child"; then
      alive=1
    fi
  fi
  if [ "$alive" -eq 1 ]; then
    sleep 2
    for pid in "$replay_pid" "$sonic_pid" "$sim_pid" "$gemx_pid" "$render_pid"; do
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill -KILL -"$pid" 2>/dev/null || true
      fi
    done
    if [ -n "${sonic_child:-}" ] && kill -0 "$sonic_child" 2>/dev/null; then
      kill -KILL -"$sonic_child" 2>/dev/null || true
    fi
  fi
  write_timings
  exit "$status"
}

require_absent() {
  local pattern=$1
  if pgrep -f "$pattern" >/dev/null; then
    echo "refusing to start while $pattern is already running" >&2
    pgrep -af "$pattern" >&2 || true
    exit 2
  fi
}

wait_until_dead() {
  local pid=$1
  local label=$2
  local ticks=$3
  local i
  for ((i = 0; i < ticks; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  echo "SHOWHAND_DRIVER_FAIL: $label pid $pid still alive after timeout" >&2
  return 1
}

if [ -z "${NEBIUS_API_KEY-}" ]; then
  echo "NEBIUS_API_KEY is unset" >&2
  exit 2
fi
echo "NEBIUS_API_KEY_LENGTH=${#NEBIUS_API_KEY}"

if [[ ! "$run_id" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "run id must use 1-128 ASCII letters, digits, dots, underscores, or hyphens" >&2
  exit 2
fi
take_stem=$(basename "$take_video")
take_stem=${take_stem%.*}
if [[ "$take_stem" == pexels_* || "$take_stem" == Pexels_* ]]; then
  echo "refusing to label a Pexels clip as Stephen's take" >&2
  exit 2
fi
if [ ! -f "$take_video" ]; then
  echo "take video does not exist: $take_video" >&2
  exit 2
fi
if [ -e "$output_root" ]; then
  echo "refusing existing OUTPUT_ROOT: $output_root" >&2
  exit 2
fi

rel_out=$(realpath -m --relative-to="$repo" "$output_root")
case "$rel_out" in
  ""|/*|..|../*) echo "OUTPUT_ROOT must be inside the repository" >&2; exit 2 ;;
esac
if ! git -C "$repo" check-ignore -q -- "$rel_out"; then
  echo "OUTPUT_ROOT must be gitignored so replay stays clean: $rel_out" >&2
  exit 2
fi
dirty=$(git -C "$repo" status --porcelain --untracked-files=all)
if [ -n "$dirty" ]; then
  echo "repository is dirty; replay would refuse" >&2
  printf '%s\n' "$dirty" >&2
  exit 2
fi
threshold_commit=$(git -C "$repo" rev-list -1 HEAD -- config/thresholds.yaml)
if [ "$threshold_commit" != "$frozen_threshold_commit" ]; then
  echo "threshold commit is $threshold_commit, want $frozen_threshold_commit" >&2
  exit 2
fi
require_absent g1_deploy_onnx_ref
require_absent run_instrumented_sim.py
require_absent demo_soma_onnx.py
require_absent replay_soma_v3.py
require_absent drive_sonic_pty.py
if ss -H -ltn "sport = :5556" | grep -q ':5556'; then
  echo "port 5556 is already in use" >&2
  exit 2
fi
gpu_apps=$(nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader)
if [ -n "$gpu_apps" ]; then
  echo "refusing to start while a GPU compute process is running" >&2
  printf '%s\n' "$gpu_apps" >&2
  exit 2
fi

probe_json=$(python3 - "$take_video" <<'PY'
import json
import subprocess
import sys

raw = subprocess.check_output(
    [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,nb_frames,duration:format=duration",
        "-of",
        "json",
        sys.argv[1],
    ],
    text=True,
)
payload = json.loads(raw)
stream = payload["streams"][0]
rate = stream["avg_frame_rate"]
num, den = rate.split("/")
num_i, den_i = int(num), int(den)
if den_i == 0 or num_i % den_i != 0:
    raise SystemExit(f"source fps {rate} is not an integer")
frames = stream.get("nb_frames")
container_frames = int(frames) if frames and frames != "N/A" else None
duration = stream.get("duration") or payload.get("format", {}).get("duration")
print(
    json.dumps(
        {
            "fps": num_i // den_i,
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "container_frames": container_frames,
            "container_duration_s": float(duration) if duration else None,
        }
    )
)
PY
)
source_fps=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["fps"])' "$probe_json")

mkdir -p "$output_root/driver" "$output_root/logs" "$output_root/sim" "$output_root/gemx"
printf '%s\n' "$probe_json" > "$output_root/driver/probe.json"
: > "$output_root/driver/timing.tsv"
trap cleanup EXIT INT TERM

cp -- "$take_video" "$output_root/source.mp4"
source_hash=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$take_video")
copy_hash=$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$output_root/source.mp4")
if [ "$source_hash" != "$copy_hash" ]; then
  die "copied source bytes differ from the take"
fi

current_log=$output_root/logs/gemx.log
echo "SHOWHAND_STAGE=gemx_start"
gemx_start=$(date +%s%N)
setsid bash "$repo/tools/wsl/run_gemx_offline.sh" "$take_video" "$output_root/gemx" \
  >"$current_log" 2>&1 &
gemx_pid=$!
set +e
wait "$gemx_pid"
gemx_status=$?
set -e
gemx_pid=""
append_timing gem_x_offline_s "$(elapsed_s "$gemx_start" "$(date +%s%N)")"
if [ "$gemx_status" -ne 0 ]; then
  die "GEM-X exited $gemx_status"
fi
hpe_results=$output_root/gemx/$take_stem/hpe_results.pt
retarget_csv=$output_root/gemx/$take_stem/${take_stem}_retarget_g1.csv
if [ ! -f "$hpe_results" ] || [ ! -f "$retarget_csv" ]; then
  die "GEM-X finished without $hpe_results and $retarget_csv"
fi
echo "SHOWHAND_STAGE=gemx_done"

handshake=/tmp/showhand-handshake-$run_id
sonic_native=/tmp/showhand-sonic-$run_id
rm -f "$handshake"
if [ -e "$sonic_native" ]; then
  die "refusing existing SONIC log directory $sonic_native"
fi

cat > "$output_root/driver/sim.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source /home/stephensookra/showhand/env.sh
source "$sonic_root/.venv_sim/bin/activate"
cd "$sonic_root"
exec python $(printf '%q' "$repo/tools/wsl/run_instrumented_sim.py") \\
  --telemetry $(printf '%q' "$output_root/sim/telemetry.csv") \\
  --sim-meta $(printf '%q' "$output_root/sim/sim_meta.json") \\
  --handshake-socket $(printf '%q' "$handshake")
EOF
chmod +x "$output_root/driver/sim.sh"
current_log=$output_root/logs/sim.log
echo "SHOWHAND_STAGE=sim_start"
sim_start=$(date +%s%N)
setsid "$output_root/driver/sim.sh" >"$current_log" 2>&1 &
sim_pid=$!
printf '%s\n' "$sim_pid" > "$output_root/driver/sim.pid"
for ((i = 0; i < 1200; i++)); do
  if grep -q 'SHOWHAND_SIM_INSTRUMENTATION=active' "$current_log" && [ -S "$handshake" ]; then
    break
  fi
  if ! kill -0 "$sim_pid" 2>/dev/null; then
    die "simulator exited before instrumentation was active"
  fi
  sleep 0.1
done
if ! grep -q 'SHOWHAND_SIM_INSTRUMENTATION=active' "$current_log"; then
  die "simulator did not report instrumentation"
fi
append_timing simulator_start_to_ready_s "$(elapsed_s "$sim_start" "$(date +%s%N)")"
echo "SHOWHAND_STAGE=sim_ready"

current_log=$output_root/logs/sonic-pty.log
echo "SHOWHAND_STAGE=sonic_start"
sonic_start=$(date +%s%N)
setsid python3 "$repo/tools/wsl/drive_sonic_pty.py" \
  --wrapper "$repo/tools/wsl/run_sonic.sh" \
  --log-dir "$sonic_native" \
  --run-id "$run_id" \
  --status-dir "$output_root/driver/sonic-status" \
  --replay-pid-file "$output_root/driver/replay.pid" \
  >"$current_log" 2>&1 &
sonic_pid=$!
printf '%s\n' "$sonic_pid" > "$output_root/driver/sonic.pid"
for ((i = 0; i < 2400; i++)); do
  if [ -f "$output_root/driver/sonic-status/init_done" ]; then
    break
  fi
  if [ -f "$output_root/driver/sonic-status/failed" ]; then
    die "SONIC arm failed: $(cat "$output_root/driver/sonic-status/failed")"
  fi
  if ! kill -0 "$sonic_pid" 2>/dev/null; then
    die "SONIC pty exited before Init Done"
  fi
  sleep 0.1
done
if [ ! -f "$output_root/driver/sonic-status/init_done" ]; then
  die "SONIC did not reach Init Done"
fi
append_timing sonic_start_to_init_done_s "$(elapsed_s "$sonic_start" "$(date +%s%N)")"
echo "SHOWHAND_STAGE=sonic_init_done"

cat > "$output_root/driver/replay.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source /home/stephensookra/showhand/env.sh
source "$gemx_root/.venv/bin/activate"
site=\$(python -c 'import site; print(site.getsitepackages()[0])')
nvidia_libs=\$(find "\$site/nvidia" -type d -name lib -print | sort | paste -sd: -)
export LD_LIBRARY_PATH="\$nvidia_libs:\${LD_LIBRARY_PATH:-}"
export CUDA_MODULE_LOADING=LAZY
exec python $(printf '%q' "$repo/tools/wsl/replay_soma_v3.py") \\
  --pt $(printf '%q' "$hpe_results") \\
  --source-fps $source_fps \\
  --output-fps 50 \\
  --smpl-output $(printf '%q' "$output_root/smpl_sequence.npz") \\
  --timing-output $(printf '%q' "$output_root/replay_timing.json") \\
  --handshake-socket $(printf '%q' "$handshake") \\
  --max-jitter-s 0.01 \\
  --post-roll-s 0.6 \\
  --publisher-warmup-s 0.5 \\
  --run-id $(printf '%q' "$run_id")
EOF
chmod +x "$output_root/driver/replay.sh"
current_log=$output_root/logs/replay.log
echo "SHOWHAND_STAGE=replay_start"
replay_start=$(date +%s%N)
setsid "$output_root/driver/replay.sh" >"$current_log" 2>&1 &
replay_pid=$!
printf '%s\n' "$replay_pid" > "$output_root/driver/replay.pid"
arm_failed=0
while kill -0 "$replay_pid" 2>/dev/null; do
  if [ -f "$output_root/driver/sonic-status/failed" ]; then
    arm_failed=1
    kill -TERM -"$replay_pid" 2>/dev/null || true
    break
  fi
  if [ -f "$current_log" ] && grep -q 'REPLAY_SOURCE_FRAMES=' "$current_log" \
    && [ ! -f "$output_root/driver/sonic-status/ready" ]; then
    arm_failed=1
    kill -TERM -"$replay_pid" 2>/dev/null || true
    echo "release reached before ZMQ control was armed" > "$output_root/driver/sonic-status/failed"
    break
  fi
  if ! kill -0 "$sonic_pid" 2>/dev/null; then
    arm_failed=1
    kill -TERM -"$replay_pid" 2>/dev/null || true
    echo "SONIC pty exited during replay" > "$output_root/driver/sonic-status/failed"
    break
  fi
  sleep 0.05
done
set +e
wait "$replay_pid"
replay_status=$?
set -e
replay_pid=""
append_timing replay_process_wall_s "$(elapsed_s "$replay_start" "$(date +%s%N)")"
if [ "$arm_failed" -ne 0 ]; then
  die "SONIC was not armed for graded replay: $(cat "$output_root/driver/sonic-status/failed")"
fi
if [ "$replay_status" -ne 0 ]; then
  die "replay exited $replay_status"
fi
if [ ! -f "$output_root/driver/sonic-status/ready" ]; then
  die "replay finished without a ZMQ-enabled marker"
fi
echo "SHOWHAND_STAGE=replay_done"

if ! wait_until_dead "$sim_pid" simulator 600; then
  signaled_sim=1
  kill -TERM -"$sim_pid" 2>/dev/null || true
  die "simulator did not exit after the finish acknowledgement"
fi
set +e
wait "$sim_pid"
sim_status=$?
set -e
sim_pid=""
if [ "$sim_status" -ne 0 ]; then
  current_log=$output_root/logs/sim.log
  die "simulator exited $sim_status"
fi

if ! wait_until_dead "$sonic_pid" sonic 600; then
  signaled_sonic=1
  kill -TERM -"$sonic_pid" 2>/dev/null || true
  die "SONIC did not exit after the simulator stopped"
fi
set +e
wait "$sonic_pid"
sonic_status=$?
set -e
sonic_pid=""
if [ "$sonic_status" -ne 0 ]; then
  current_log=$output_root/logs/sonic-pty.log
  die "SONIC pty exited $sonic_status"
fi
for ((i = 0; i < 50; i++)); do
  if [ -f "$sonic_native/console.log" ] && grep -q "SHOWHAND_RUN_END=$run_id exit=0" "$sonic_native/console.log"; then
    break
  fi
  sleep 0.1
done
if ! grep -q "SHOWHAND_RUN_END=$run_id exit=0" "$sonic_native/console.log"; then
  die "SONIC console is missing the successful run-end marker"
fi
mkdir -p "$output_root/sonic_logs"
cp -a "$sonic_native/." "$output_root/sonic_logs/"
echo "SHOWHAND_STAGE=sonic_logs_copied"

cat > "$output_root/driver/render.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source /home/stephensookra/showhand/env.sh
source "$sonic_root/.venv_sim/bin/activate"
cd "$sonic_root"
exec python $(printf '%q' "$repo/tools/wsl/render_sim_telemetry.py") \\
  --telemetry $(printf '%q' "$output_root/sim/telemetry.csv") \\
  --replay-timing $(printf '%q' "$output_root/replay_timing.json") \\
  --render $(printf '%q' "$output_root/sim/render.mp4") \\
  --render-timestamps $(printf '%q' "$output_root/sim/render_timestamps.csv") \\
  --render-meta $(printf '%q' "$output_root/sim/render_meta.json")
EOF
chmod +x "$output_root/driver/render.sh"
current_log=$output_root/logs/render.log
echo "SHOWHAND_STAGE=render_start"
render_start=$(date +%s%N)
setsid "$output_root/driver/render.sh" >"$current_log" 2>&1 &
render_pid=$!
set +e
wait "$render_pid"
render_status=$?
set -e
render_pid=""
append_timing offline_render_s "$(elapsed_s "$render_start" "$(date +%s%N)")"
if [ "$render_status" -ne 0 ]; then
  die "render exited $render_status"
fi
echo "SHOWHAND_STAGE=render_done"

win_repo=$(wslpath -w "$repo")
if [ -f "$repo/.venv/Scripts/showhand.exe" ]; then
  win_showhand=$(wslpath -w "$repo/.venv/Scripts/showhand.exe")
else
  win_showhand=$(wslpath -w "$repo/.venv/Scripts/showhand")
fi
win_csv=$(wslpath -w "$retarget_csv")
win_telemetry=$(wslpath -w "$output_root/sim/telemetry.csv")
win_timing=$(wslpath -w "$output_root/replay_timing.json")
win_meta=$(wslpath -w "$output_root/sim/sim_meta.json")
win_console=$(wslpath -w "$output_root/sonic_logs/console.log")
win_metrics=$(wslpath -w "$output_root/metrics.json")
win_record_in=$(wslpath -w "$output_root/record_input.json")
win_record=$(wslpath -w "$output_root/take_record.json")
python3 - "$output_root/driver/metrics.ps1" "$win_repo" "$win_showhand" "$win_csv" \
  "$source_fps" "$win_telemetry" "$win_timing" "$win_meta" "$win_console" "$win_metrics" <<'PY'
import sys
from pathlib import Path

ps1, repo, showhand, csv, fps, telemetry, timing, meta, console, metrics = sys.argv[1:]
Path(ps1).write_text(
    "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"Set-Location '{repo}'",
            f"& '{showhand}' metrics `",
            f"  --retarget-csv '{csv}' `",
            f"  --source-fps '{fps}' `",
            f"  --telemetry '{telemetry}' `",
            f"  --replay-timing '{timing}' `",
            f"  --sim-meta '{meta}' `",
            f"  --sonic-console '{console}' `",
            "  --thresholds 'config\\thresholds.yaml' `",
            f"  --out '{metrics}'",
            "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }",
            "",
        ]
    ),
    encoding="utf-8",
    newline="\n",
)
PY
current_log=$output_root/logs/metrics.log
echo "SHOWHAND_STAGE=metrics_start"
metrics_start=$(date +%s%N)
set +e
WSLENV=NEBIUS_API_KEY powershell.exe -NoProfile -File "$(wslpath -w "$output_root/driver/metrics.ps1")" \
  >"$current_log" 2>&1
metrics_status=$?
set -e
append_timing deterministic_metrics_s "$(elapsed_s "$metrics_start" "$(date +%s%N)")"
if [ "$metrics_status" -ne 0 ]; then
  die "metrics exited $metrics_status"
fi
echo "SHOWHAND_STAGE=metrics_done"

write_timings
sim_state=exit_0
sonic_state=exit_0
if [ "$signaled_sim" -ne 0 ]; then
  sim_state=killed_after_timeout
fi
if [ "$signaled_sonic" -ne 0 ]; then
  sonic_state=killed_after_timeout
fi
probe_args=()
while IFS= read -r arg; do
  probe_args+=("$arg")
done < <(python3 - "$output_root/driver/probe.json" <<'PY'
import json
import sys

probe = json.loads(open(sys.argv[1], encoding="utf-8").read())
if probe["container_duration_s"] is not None:
    print(f"--container-duration-s\n{probe['container_duration_s']}")
if probe["container_frames"] is not None:
    print(f"--container-frames\n{probe['container_frames']}")
print(f"--width\n{probe['width']}")
print(f"--height\n{probe['height']}")
PY
)
python3 "$repo/tools/wsl/assemble_take_record.py" \
  --repo "$repo" \
  --out "$output_root/record_input.json" \
  --take-id "$take_stem" \
  --source-path "$output_root/source.mp4" \
  --original-wsl-path "$take_video" \
  --replay-timing "$output_root/replay_timing.json" \
  --metrics "$output_root/metrics.json" \
  --telemetry "$output_root/sim/telemetry.csv" \
  --sim-meta "$output_root/sim/sim_meta.json" \
  --sonic-console "$output_root/sonic_logs/console.log" \
  --sonic-logs "$output_root/sonic_logs" \
  --smpl-sequence "$output_root/smpl_sequence.npz" \
  --render "$output_root/sim/render.mp4" \
  --render-timestamps "$output_root/sim/render_timestamps.csv" \
  --render-meta "$output_root/sim/render_meta.json" \
  --retarget-csv "$retarget_csv" \
  --hpe-results "$hpe_results" \
  --stage-timings "$output_root/driver/stage_timings.json" \
  --sim-final-state "$sim_state" \
  --sonic-final-state "$sonic_state" \
  "${probe_args[@]}"

python3 - "$output_root/driver/record.ps1" "$win_repo" "$win_showhand" "$win_record_in" "$win_record" <<'PY'
import sys
from pathlib import Path

ps1, repo, showhand, record_in, record_out = sys.argv[1:]
Path(ps1).write_text(
    "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"Set-Location '{repo}'",
            f"& '{showhand}' write-record --input '{record_in}' --out '{record_out}'",
            "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }",
            "",
        ]
    ),
    encoding="utf-8",
    newline="\n",
)
PY
current_log=$output_root/logs/record.log
echo "SHOWHAND_STAGE=write_record_start"
record_start=$(date +%s%N)
set +e
WSLENV=NEBIUS_API_KEY powershell.exe -NoProfile -File "$(wslpath -w "$output_root/driver/record.ps1")" \
  >"$current_log" 2>&1
record_status=$?
set -e
append_timing write_record_s "$(elapsed_s "$record_start" "$(date +%s%N)")"
write_timings
if [ "$record_status" -ne 0 ]; then
  die "write-record exited $record_status"
fi

python3 - "$output_root" "$take_stem" "$run_id" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
timing = json.loads((root / "replay_timing.json").read_text(encoding="utf-8"))
metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
stages = json.loads((root / "driver" / "stage_timings.json").read_text(encoding="utf-8"))
overall = metrics["overall"]
summary = {
    "label": "Stephen's take",
    "take_id": sys.argv[2],
    "run_id": sys.argv[3],
    "stage_timings_s": stages,
    "soma_to_smpl_precompute_s": timing["conversion_wall_s"],
    "sonic_replay_50_hz_s": timing["wall_duration_s"],
    "sonic_received_frames": timing["output_frames"],
    "sonic_expected_frames": timing["output_frames"],
    "sonic_final_frame": timing["expected_final_frame_index"],
    "publish_jitter_max_s": timing["publish_jitter_max_s"],
    "tracking_mean_abs_error_rad": overall["tracking_mean_abs_error_rad"],
    "tracking_p95_abs_error_rad": overall["tracking_p95_abs_error_rad"],
    "falls": overall["falls"],
    "out_of_balance_seconds": overall["out_of_balance_seconds"],
    "deterministic_pass": overall["pass"],
    "reason_codes": overall["reason_codes"],
    "render": str(root / "sim" / "render.mp4"),
    "take_record": str(root / "take_record.json"),
}
text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
(root / "driver" / "summary.json").write_text(text, encoding="utf-8")
print(text, end="")
PY
echo "SHOWHAND_STAGE=done"

leftover=0
for pattern in g1_deploy_onnx_ref run_instrumented_sim.py replay_soma_v3.py drive_sonic_pty.py; do
  if pgrep -f "$pattern" >/dev/null; then
    echo "SHOWHAND_DRIVER_FAIL: leftover process $pattern" >&2
    pgrep -af "$pattern" >&2 || true
    pkill -TERM -f "$pattern" || true
    leftover=1
  fi
done
if [ "$leftover" -ne 0 ]; then
  sleep 2
  exit 1
fi
