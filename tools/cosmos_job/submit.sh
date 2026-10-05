#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: submit.sh TAKE_ID PAIRS_DIR [nebius create args...]" >&2
  exit 2
fi
take_id="$1"
pairs_dir="$2"
shift 2
here=$(cd "$(dirname "$0")" && pwd)
nebius_cli="/home/stephensookra/.nebius/bin/nebius"
image="pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime@sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be"

test -f "$pairs_dir/manifest.json"
inject_args=(--inject-file "$pairs_dir/manifest.json:/inject/pairs/manifest.json")
while IFS= read -r pair; do
  size=$(stat -c %s "$pair")
  if [ "$size" -gt 65536 ]; then
    echo "pair exceeds Nebius 65536-byte injected-file limit: $pair ($size bytes)" >&2
    exit 1
  fi
  inject_args+=(--inject-file "$pair:/inject/pairs/$(basename "$pair")")
done < <(find "$pairs_dir" -maxdepth 1 -type f -name 'window-*.jpg' | sort)
if [ "${#inject_args[@]}" -eq 2 ]; then
  echo "no pair images found in $pairs_dir" >&2
  exit 1
fi
"$nebius_cli" --profile hackathon ai job create \
  --name "showhand-cosmos-${take_id}-$(date -u +%Y%m%d%H%M)" \
  --image "$image" \
  --parent-id project-e00mwywjpr00x87mxbjn98 \
  --platform gpu-l40s-a \
  --preset 1gpu-8vcpu-32gb \
  --timeout 45m \
  --disk-size 100Gi \
  --inject-file "$here/visual_judge.py:/inject/visual_judge.py" \
  --inject-file "$here/run.sh:/inject/run.sh" \
  "${inject_args[@]}" \
  --container-command bash \
  --args "/inject/run.sh $take_id" \
  "$@"
