#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: fetch.sh JOB_ID TAKE_ID MANIFEST_JSON OUTPUT_JSON" >&2
  exit 2
fi
job_id="$1"
take_id="$2"
manifest="$3"
output="$4"
here=$(cd "$(dirname "$0")" && pwd)
nebius_cli="/home/stephensookra/.nebius/bin/nebius"
log_file=$(mktemp)
job_file=$(mktemp)
trap 'rm -f "$log_file" "$job_file"' EXIT

"$nebius_cli" --profile hackathon ai job get "$job_id" --format json > "$job_file"
"$nebius_cli" --profile hackathon ai logs "$job_id" --since 168h --tail 1000 > "$log_file"
grep -q "=== COSMOS_JSON_BEGIN $take_id" "$log_file"
grep -q "=== COSMOS_JSON_END $take_id" "$log_file"
mkdir -p "$(dirname "$output")"
sed -n "/=== COSMOS_JSON_BEGIN $take_id/,/=== COSMOS_JSON_END $take_id/p" "$log_file" \
  | sed '1d;$d' | base64 -d | gunzip > "${output}.tmp"
python "$here/validate_result.py" \
  --job "$job_file" \
  --result "${output}.tmp" \
  --manifest "$manifest" \
  --take-id "$take_id"
mv "${output}.tmp" "$output"
