#!/usr/bin/env bash
# Offline smoke: mock wget via PATH; mock Python helpers to no-op DB.
# Run: bash tests/test_npu_sync_bash.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="${ROOT}/tests/fixtures/npu"
MOCK_BIN="$(mktemp -d)"
trap 'rm -rf "${MOCK_BIN}"' EXIT

# Fake wget: copy fixtures based on URL shape; honor -O / --timeout / --tries only
cat > "${MOCK_BIN}/wget" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
out=""
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -O) out="$2"; shift 2 ;;
    --timeout=*|--tries=*) shift ;;
    --timeout|--tries) shift 2 ;;
    http*|HTTP*) url="$1"; shift ;;
    *)
      echo "unexpected wget option: $1" >&2
      exit 2
      ;;
  esac
done
: "${out:?wget mock missing -O}"
: "${url:?wget mock missing url}"
# URL must be last positional recorded; options already consumed
# Record calls for assertions
echo "${url}" >> "${MOCK_BIN}/wget-calls.txt"
FIXTURES_DIR="${FIXTURES_DIR:?}"
if [[ "${url}" == *"/query?"* ]]; then
  if [[ "${url}" == *"returnIdsOnly"* ]]; then
    # First list page has ids; subsequent empty (offset>0 simulated by call count)
    n=$(wc -l < "${MOCK_BIN}/wget-calls.txt" | tr -d ' ')
    # calls: 1=meta, 2=list, 3+=detail or next list
    if [[ "${url}" == *"resultOffset=0"* ]] || [[ "${url}" != *"resultOffset="* ]]; then
      cp "${FIXTURES_DIR}/pamatky-ids.json" "${out}"
    else
      cp "${FIXTURES_DIR}/pamatky-ids-empty.json" "${out}"
    fi
  else
    cp "${FIXTURES_DIR}/detail.geojson" "${out}"
  fi
else
  cp "${FIXTURES_DIR}/meta.json" "${out}"
fi
exit 0
EOF
chmod +x "${MOCK_BIN}/wget"

# Fake uv/python: implement only the helper subcommands used by the script
cat > "${MOCK_BIN}/uv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# uv run python -m sample_db_backend.sync.npu_geoportal …
shift  # run
shift  # python
shift  # -m
shift  # sample_db_backend.sync.npu_geoportal
cmd="${1:-}"; shift || true
case "$cmd" in
  page-size) echo 1000 ;;
  layer-name) echo "Test Layer" ;;
  extract-ids)
    path="$1"
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1]));
[print(i) for i in (d.get("objectIds") or [])]' "$path"
    ;;
  ensure-layer) echo "00000000-0000-0000-0000-000000000001" ;;
  upsert-file)
    path="$1"
    n=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(len(d.get("features") or []))' "$path")
    echo "${n}/${n}"
    ;;
  *) echo "unexpected cmd: $cmd" >&2; exit 1 ;;
esac
EOF
chmod +x "${MOCK_BIN}/uv"

export PATH="${MOCK_BIN}:${PATH}"
export FIXTURES_DIR="${FIXTURES}"
export DATABASE_URL='postgresql://unused'
export NPU_LAYER_URL='https://example.test/MapServer/0'
export NPU_DETAIL_BATCH=2
export NPU_MAX_RETRIES=0
export MOCK_BIN

# sleep no-op not needed (no retries)

bash "${ROOT}/scripts/sample-db-npu-sync"

calls="$(cat "${MOCK_BIN}/wget-calls.txt")"
echo "wget calls:"
echo "${calls}"

# Expect: meta, list (offset 0), then detail batches for 101,102 and 103, then maybe stop
echo "${calls}" | grep -q '?f=json'
echo "${calls}" | grep -q 'returnIdsOnly=true'
echo "${calls}" | grep -q 'objectIds='
echo "${calls}" | grep -q 'f=geojson'

echo "OK: bash orchestrator smoke passed (mocked wget + helpers)"
