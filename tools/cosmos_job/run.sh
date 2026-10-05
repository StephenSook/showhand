#!/usr/bin/env bash
set -euo pipefail

take_id="$1"
mkdir -p /work/pairs
cp /inject/visual_judge.py /work/visual_judge.py
cp /inject/pairs/manifest.json /work/pairs/manifest.json
cp /inject/pairs/window-*.jpg /work/pairs/

export PIP_BREAK_SYSTEM_PACKAGES=1
pip install --quiet --no-cache-dir \
  transformers==5.6.1 accelerate==1.12.0 qwen-vl-utils==0.0.14 \
  pillow==12.3.0 torchvision==0.26.0 av==16.1.0

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
start_ns=$(date +%s%N)
python /work/visual_judge.py \
  --take-id "$take_id" \
  --manifest /work/pairs/manifest.json \
  --output "/work/${take_id}.visual.json"
end_ns=$(date +%s%N)
echo "COSMOS_WALL_S=$(python -c "print(($end_ns-$start_ns)/1e9)")"
echo "=== COSMOS_JSON_BEGIN $take_id"
gzip -c "/work/${take_id}.visual.json" | base64 -w 1000
echo "=== COSMOS_JSON_END $take_id"
