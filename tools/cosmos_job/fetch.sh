#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: fetch.sh JOB_ID TAKE_ID OUTPUT_JSON" >&2
  exit 2
fi
job_id="$1"
take_id="$2"
output="$3"
nebius_cli="/home/stephensookra/.nebius/bin/nebius"
log_file=$(mktemp)
trap 'rm -f "$log_file"' EXIT

"$nebius_cli" --profile hackathon ai logs "$job_id" --since 168h --tail 1000 > "$log_file"
grep -q "=== COSMOS_JSON_BEGIN $take_id" "$log_file"
grep -q "=== COSMOS_JSON_END $take_id" "$log_file"
mkdir -p "$(dirname "$output")"
sed -n "/=== COSMOS_JSON_BEGIN $take_id/,/=== COSMOS_JSON_END $take_id/p" "$log_file" \
  | sed '1d;$d' | base64 -d | gunzip > "${output}.tmp"
python -c 'import json,sys; value=json.load(open(sys.argv[1])); print(value["model_id"], len(value["verdicts"]))' "${output}.tmp"
mv "${output}.tmp" "$output"
