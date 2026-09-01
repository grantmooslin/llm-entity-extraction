#!/usr/bin/env bash
# Durability gate — production readiness scoreboard for the full agent roster.
#
# Runs every role's bench against BOTH registry models and prints a per-agent
# scoreboard. Gate policy (v1): report-only; wire thresholds into CI once
# baselines stabilize for 2 consecutive runs.
#
# Usage: scripts/durability_gate.sh [limit-per-suite]   # default 6
set -uo pipefail
cd "$(dirname "$0")/.."

LIMIT="${1:-6}"
MODELS=("stealth/ox-alpha" "deepseek/deepseek-v4-flash")  # TEMP: ox-alpha cost swap
SPECIALISTS=(contracts_specialist corporate_records_specialist correspondence_specialist insurance_claims_specialist)

echo "== regenerating edge suites =="
python3 scripts/gen_edge_cases.py --all >/dev/null

for m in "${MODELS[@]}"; do
  ms=$(echo "$m" | tr '/' '_')
  echo ""
  echo "===== MODEL: $m ====="
  for a in "${SPECIALISTS[@]}"; do
    python3 scripts/run_agent_bench.py --mode edge --agent "$a" --model "$m" \
      --limit "$LIMIT" 2>/dev/null | grep -E "no_fabrication|edge bench" | sed "s/^/  [$a] /"
  done
  python3 scripts/run_agent_bench.py --mode judge-mutation --model "$m" \
    --prompt-version judge_correctness_docclass_pilot_v1 --limit "$LIMIT" \
    2>/dev/null | grep -E "recall|FPR" | sed 's/^/  [judge_correctness] /'
  for role in arbiter boss; do
    python3 scripts/run_agent_bench.py --mode conflicts --role "$role" --model "$m" \
      --limit "$LIMIT" 2>/dev/null | grep -E "correct" | sed "s/^/  [$role] /"
  done
done

echo ""
echo "== Langfuse sync of edge suites (manual step) =="
cat <<'PY'
# Sync a suite into The-Mailroom's Langfuse env as a dataset:
#   from dotenv import load_dotenv; load_dotenv("path/to/The-Mailroom/.env")
#   from langfuse import Langfuse
#   import json
#   lf = Langfuse()
#   lf.create_dataset(name="edge-contracts-specialist", description="durability matrix")
#   for line in open("data/gt/edge_suites/edge_contracts_specialist.jsonl"):
#       it = json.loads(line)
#       lf.create_dataset_item(dataset_name="edge-contracts-specialist",
#           id=it["suite_id"], input={"filename": it["base_filename"], "doc_text": it["doc_text"]},
#           expected_output=it["expectations"], metadata={"transform": it["transform"]})
PY
echo "gate complete."
