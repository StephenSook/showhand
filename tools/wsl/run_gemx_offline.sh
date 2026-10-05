#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: run_gemx_offline.sh CLIP OUTPUT_ROOT" >&2
  exit 2
fi

clip="$1"
output_root="$2"
gemx_root="/home/stephensookra/showhand/GEM-X"

test -f "$clip"
mkdir -p "$output_root"
source /home/stephensookra/showhand/env.sh
source "$gemx_root/.venv/bin/activate"
cd "$gemx_root"

site=$(python -c 'import site; print(site.getsitepackages()[0])')
nvidia_libs=$(find "$site/nvidia" -type d -name lib -print | sort | paste -sd: -)
export LD_LIBRARY_PATH="$nvidia_libs:${LD_LIBRARY_PATH:-}"
export CUDA_MODULE_LOADING=LAZY

echo "GEMX_MODEL=nvidia/GEM-X"
echo "GEMX_COMMIT=$(git rev-parse HEAD)"
echo "GEMX_START=$(date --iso-8601=ns)"
start_ns=$(date +%s%N)
set +e
python scripts/demo/demo_soma_onnx.py \
  --video "$clip" \
  --output_root "$output_root" \
  --retarget
status=$?
set -e
end_ns=$(date +%s%N)
echo "GEMX_EXIT=$status"
echo "GEMX_WALL_S=$(python -c "print(($end_ns-$start_ns)/1e9)")"
echo "GEMX_END=$(date --iso-8601=ns)"
exit "$status"
