#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: run_sonic.sh LOG_DIRECTORY" >&2
  exit 2
fi

deploy_root="/home/stephensookra/showhand/GR00T-WholeBodyControl/gear_sonic_deploy"
log_dir="$1"
mkdir -p "$log_dir"
source /home/stephensookra/showhand/env.sh
cd "$deploy_root"

echo "SONIC_START=$(date --iso-8601=ns)"
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
echo "SONIC_EXIT=$status"
echo "SONIC_END=$(date --iso-8601=ns)"
exit "$status"
