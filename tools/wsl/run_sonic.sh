#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: run_sonic.sh LOG_DIRECTORY RUN_ID" >&2
  exit 2
fi

deploy_root="/home/stephensookra/showhand/GR00T-WholeBodyControl/gear_sonic_deploy"
log_dir="$1"
run_id="$2"
if [ -e "$log_dir" ]; then
  echo "refusing reused SONIC log directory: $log_dir" >&2
  exit 2
fi
mkdir "$log_dir"
exec > >(tee "$log_dir/console.log") 2>&1
source /home/stephensookra/showhand/env.sh
cd "$deploy_root"

echo "SONIC_START=$(date --iso-8601=ns)"
echo "SHOWHAND_RUN_BEGIN=$run_id"
set +e
target/release/g1_deploy_onnx_ref \
  eth0 policy/release/model_decoder.onnx reference/example/ \
  --obs-config policy/release/observation_config.yaml \
  --encoder-file policy/release/model_encoder.onnx \
  --planner-file planner/target_vel/V2/planner_sonic.onnx \
  --input-type zmq \
  --output-type all \
  --zmq-host localhost \
  --disable-crc-check \
  --enable-csv-logs \
  --logs-dir "$log_dir"
status=$?
set -e
echo "SONIC_EXIT=$status"
echo "SONIC_END=$(date --iso-8601=ns)"
echo "SHOWHAND_RUN_END=$run_id exit=$status"
exit "$status"
