#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: submit.sh TAKE_ID PAIRS_TAR_GZ [nebius create args...]" >&2
  exit 2
fi
take_id="$1"
pairs_archive="$2"
shift 2
here=$(cd "$(dirname "$0")" && pwd)
nebius_cli="/home/stephensookra/.nebius/bin/nebius"
image="pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime@sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be"

test -f "$pairs_archive"
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
  --inject-file "$pairs_archive:/inject/pairs.tar.gz" \
  --container-command bash \
  --args "/inject/run.sh $take_id" \
  "$@"
