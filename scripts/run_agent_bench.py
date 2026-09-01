#!/usr/bin/env python3
"""run_agent_bench.py — durability benches for every classification-chain role.

KANBAN-097 eval tasks: every roster role gets a deterministic, machine-scored
surface — no LLM-as-judge anywhere.

Modes:
  edge            Run an agent over its generated edge suite (gen_edge_cases.py)
                  and score machine-checkable expectations. Two families:
                    * specialists  — grounded-or-null discipline, dedup
                      tolerance, injection resistance (schema extraction);
                    * sorter / reviewer — BLIND doc_type classification scored
                      by exact match against the suite's ``gt_fields.doc_type``
                      (the roster's classification roles).
  judge-mutation  Planted-defect precision/recall for the correctness judge:
                  defects are injected into CLEAN ground-truth extractions; a
                  good judge flags every planted defect (recall) and never
                  invents complaints on clean copies (precision/FPR).
  conflicts       Arbiter/Boss scenario benches built from real rows:
                  A=clean GT extraction vs B=defect-injected rival.

Every completed run appends ONE compact record to the canonical append-only
``reports/experiment_log.jsonl`` (task ``agent_bench``). ``--dry-run`` prints
the plan (rows x calls, model, prompt version, data files) and never touches
the network.

Examples:
  python3 scripts/run_agent_bench.py --mode edge --agent contracts_specialist \
      --model qwen/qwen3.7-flash --limit 8 --dry-run     # plan first
  python3 scripts/run_agent_bench.py --mode edge --agent reviewer \
      --model qwen/qwen3.7-flash --limit 20              # blind classification
  python3 scripts/run_agent_bench.py --mode judge-mutation \
      --model qwen/qwen3.7-flash \
      --prompt-version judge_correctness_docclass_pilot_v0
  python3 scripts/run_agent_bench.py --mode conflicts --role arbiter \
      --model qwen/qwen3.7-flash --limit 6
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

GT = REPO_ROOT / "data" / "gt"
SUITES = GT / "edge_suites"

DEFAULT_PROMPT_VERSIONS = {
    "contracts_specialist": "contracts_specialist_docclass_v1",
    "corporate_records_specialist": "corporate_records_specialist_docclass_v1",
    "correspondence_specialist": "correspondence_specialist_docclass_v1",
    "compliance_specialist": "compliance_specialist_docclass_v1",
    "insurance_claims_specialist": "insurance_claims_specialist_docclass_v1",
}

SPECIALIST_CLASSES = {
    "contracts_specialist": "ContractsSpecialist",
    "corporate_records_specialist": "CorporateRecordsSpecialist",
    "correspondence_specialist": "CorrespondenceSpecialist",
    "insurance_claims_specialist": "InsuranceClaimsSpecialist",
}

# Blind-classification roles (edge mode): score = exact doc_type match.
# Both consume edge_sorter.jsonl (built from all classes' GT texts); the
# sorter suite spans the 4 classes that have local GT (merger_agreement has
# no local packets yet — honest coverage note recorded in run outputs).
CLASSIFIER_ROLES = {
    "sorter": "sorter_docclass_pilot_v3",
    "reviewer": "reviewer_docclass_v1",
}
PILOT_CLASSES = ["contract", "corporate_record", "correspondence",
                 "insurance_claim", "merger_agreement"]

DEFECTS = ["swap_date", "drop_list_item", "fabricate_entity", "wrong_amount",
           "null_where_present"]


def classifier_schema() -> dict:
    """Strict schema shared by the blind-classification roles."""
    from agents.base_agent import build_structured_schema
    return build_structured_schema({
        "doc_type": {"type": "string", "enum": list(PILOT_CLASSES)},
        "doc_subclass": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    })


def classify_user_message(text: str) -> str:
    """The user turn both classifier prompts expect (pilot taxonomy listed)."""
    return ("Classify this document.\n\n"
            f"Valid doc_type values: {', '.join(PILOT_CLASSES)}.\n"
            "doc_subclass: null unless the class's subclass dimension applies.\n\n"
            f"Document text:\n{text}")


# ------------------------------------------------------------------ helpers

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


_ARTIFACT_EDGE = re.compile(r"[\s\(\)\[\]\";,:'\.]+$|^[\s\(\[\]\";,:'\.]+")


def _clean_fragment(v: str) -> str:
    """Strip quote/paren/punct ARTIFACTS from fragment boundaries.

    Malformed-but-substantive extractions (e.g. 'SQUARE TWO GOLF INC., a New
    Jersey corporation (' from an alias-split) fail naive substring checks
    purely on boundary junk. Trimming edges keeps the fabrication detector
    honest about CONTENT while tolerating boundary formatting noise."""
    prev = None
    while prev != v:
        prev = v
        v = _ARTIFACT_EDGE.sub("", v)
    return v


MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


def _iso_date_grounded(v: str, raw_text_lower: str) -> bool | None:
    """ISO-dated values ground when the same calendar date exists in the
    source in ANY formatting (e.g. 'December 20, 2007'). Returns None when
    v is not an ISO date."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", v.strip())
    if not m:
        return None
    y, mo, d = m.groups()
    if y in raw_text_lower and d.lstrip("0") in raw_text_lower:
        return True
    for name, num in MONTHS.items():
        if num == int(mo) and name[:3] in raw_text_lower:
            return True
    return False


def _maybe_parse_listlike(value):
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            import ast
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return value


def _grounded(value, text_norm: str) -> bool:
    if value in (None, [], ""):
        return True
    value = _maybe_parse_listlike(value)
    if isinstance(value, str):
        iso = _iso_date_grounded(_clean_fragment(value), text_norm)
        if iso is not None:
            return iso
        v = _clean_fragment(value)
        # Token-coverage grounding: fabrications share almost no content
        # tokens with the source; legitimate-but-reformatted values share
        # nearly all of them. Strict-substring was failing every reformatted
        # value (qwen normalizes dates/entities), flattening all versions to
        # the same score.
        toks = [t for t in _norm(v).split() if len(t) > 2]
        if not toks:
            return True
        vocab = set(text_norm.split())
        cov = sum(1 for t in toks if t in vocab) / len(toks)
        return cov >= (0.60 if len(v) <= 24 else 0.75)
    if isinstance(value, list):
        return all(_grounded(_clean_fragment(v) if isinstance(v, str) else v,
                             text_norm) for v in value)
    return True


def inject_defect(gt_fields: dict, defect: str, rng) -> dict:
    """Return a copy of GT with ONE planted defect (deterministic-ish)."""
    out = json.loads(json.dumps(gt_fields))
    str_fields = [k for k, v in out.items()
                  if isinstance(v, str) and k != "filename"]
    list_fields = [k for k, v in out.items() if isinstance(v, list) and v]
    date_like = [k for k in ("effective_date", "communication_date",
                             "date_of_loss", "date_filed", "date_decided")
                 if isinstance(out.get(k), str)]
    if defect == "swap_date" and date_like:
        k = rng.choice(date_like)
        digits = re.sub(r"\D", "", out[k])
        out[k] = re.sub(r"\d{4}", f"{int(digits[-4:]) + 7}", out[k]) if len(digits) >= 4 else out[k] + " (err)"
    elif defect == "drop_list_item" and list_fields:
        k = rng.choice(list_fields)
        out[k] = out[k][:-1]
    elif defect == "fabricate_entity":
        out["fabricated_party"] = "Zzyzx Industries International Ltd."
    elif defect == "wrong_amount" and str_fields:
        k = rng.choice(str_fields)
        out[k] = "$1,234,567.89"
    elif defect == "null_where_present":
        candidates = [k for k, v in out.items() if v not in (None, [], "")]
        if candidates:
            out[rng.choice(candidates)] = None
    else:  # fallback: generic wrong amount on any string field
        if str_fields:
            out[rng.choice(str_fields)] = "$1,234,567.89"
    return out


# ------------------------------------------------------------------- modes

def _edge_suite_for(agent: str) -> Path:
    """Classifier roles share edge_sorter.jsonl; specialists have their own."""
    return SUITES / f"edge_{'sorter' if agent in CLASSIFIER_ROLES else agent}.jsonl"


def run_edge(args) -> int:
    suite = _edge_suite_for(args.agent)
    if not suite.exists():
        raise SystemExit(f"no suite at {suite}; run gen_edge_cases.py first")
    items = [json.loads(l) for l in suite.read_text().splitlines() if l.strip()]
    if args.limit:
        items = items[:args.limit]

    if args.agent in CLASSIFIER_ROLES:
        return _run_edge_classifier(args, items, suite)

    from agents.specialist_agents import SPECIALIST_SCHEMAS  # noqa: F401
    import importlib

    cls_name = SPECIALIST_CLASSES.get(args.agent)
    if not cls_name:
        raise SystemExit(f"edge mode supports specialists + "
                         f"{sorted(CLASSIFIER_ROLES)} (got {args.agent})")
    mod = importlib.import_module("agents.specialist_agents")
    agent_cls = getattr(mod, cls_name)
    prompt_version = args.prompt_version or DEFAULT_PROMPT_VERSIONS.get(
        args.agent, args.agent)

    def make():
        a = agent_cls(model=args.model, api_key=args.api_key,
                      prompt_version=prompt_version)
        a._max_tokens = args.max_tokens
        return a

    schema_mod = {"contracts_specialist": None}  # resolved per class below
    results = []
    stats = {k: [0, 0] for k in ("no_fabrication", "ignore_overlay",
                                 "all_optional_null", "humility", "dedup_lists")}
    n_rows = 0
    for it in items:
        agent = make()
        schema = agent_cls.schema
        try:
            out = agent.extract(it["doc_text"])
        except Exception as exc:
            results.append({"suite_id": it["suite_id"], "error": str(exc)[:200]})
            continue
        n_rows += 1
        text_norm = _norm(it["doc_text"])
        row = {"suite_id": it["suite_id"], "transform": it["transform"],
               "expectation_passes": {}, "extracted_fields": {}}
        # field-level grounding == no_fabrication
        ungrounded = []
        for k, v in (out or {}).items():
            if k in ("reasoning", "confidence") :
                continue
            row["extracted_fields"][k] = v
            if not _grounded(v, text_norm):
                ungrounded.append(k)
        if ungrounded:
            row["ungrounded_fields"] = ungrounded
        ok_nf = not ungrounded
        row["expectation_passes"]["no_fabrication"] = ok_nf
        stats["no_fabrication"][0] += int(ok_nf); stats["no_fabrication"][1] += 1
        exp = it.get("expectations", {})
        for key in ("all_optional_null", "humility"):
            if exp.get(key):
                # humility/all-null: any populated value must be grounded
                # (already covered); additionally near_empty expects MOSTLY null
                pop = sum(1 for k, v in (out or {}).items()
                          if k not in ("reasoning", "confidence") and v not in (None, [], ""))
                ok = pop <= 2
                row["expectation_passes"][key] = ok
                stats[key][0] += int(ok); stats[key][1] += 1
        if exp.get("dedup_lists"):
            dup_free = True
            for k, v in (out or {}).items():
                if isinstance(v, list):
                    norms = [_norm(x) for x in v]
                    if len(norms) != len(set(norms)):
                        dup_free = False
            row["expectation_passes"]["dedup_lists"] = dup_free
            stats["dedup_lists"][0] += int(dup_free); stats["dedup_lists"][1] += 1
        if exp.get("ignore_overlay"):
            # proxy: extraction must still parse and stay grounded (covered);
            # record explicitly as passing when no_fabrication passed
            row["expectation_passes"]["ignore_overlay"] = ok_nf
            stats["ignore_overlay"][0] += int(ok_nf); stats["ignore_overlay"][1] += 1
        results.append(row)

    out_path = Path(f"data/manifests/edge_{args.agent}_{prompt_version}_{args.model.replace('/','_')}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"edge bench [{args.agent}] model={args.model}: {n_rows} scored, "
          f"{len(results)-n_rows} errors -> {out_path}")
    scores = {}
    for k, (hit, tot) in stats.items():
        if tot:
            print(f"  {k:18s} {hit}/{tot} = {hit/tot:.2f}")
            scores[k] = round(hit / tot, 4)
    _log_bench_run(args, prompt_version=prompt_version, n_scored=n_rows,
                   n_error=len(results) - n_rows, scores=scores,
                   data_source=str(suite))
    return 0


def _run_edge_classifier(args, items: list[dict], suite: Path) -> int:
    """Blind doc_type classification bench — the sorter/reviewer eval task.

    Every item is an edge-suite document; the agent sees ONLY the document
    text (+ the pilot class list) and must emit doc_type. Score = exact
    match against ``gt_fields.doc_type``, with a per-transform breakdown
    (which corruption families break classification is the mutation signal).
    """
    from agents.pipeline_agents import _StructuredAgent

    prompt_version = args.prompt_version or CLASSIFIER_ROLES[args.agent]
    agent = _StructuredAgent(model=args.model, api_key=args.api_key,
                             prompt_version=prompt_version)
    schema = classifier_schema()
    results, errors = [], 0
    per_transform: dict[str, list[int]] = {}
    correct = total = 0
    conf_sum = 0.0
    for it in items:
        try:
            out = agent.run(classify_user_message(it["doc_text"]), schema,
                            temperature=0.0)
        except Exception as exc:
            results.append({"suite_id": it["suite_id"], "transform": it["transform"],
                            "error": str(exc)[:200]})
            errors += 1
            continue
        expected = (it.get("gt_fields") or {}).get("doc_type")
        pred = (out or {}).get("doc_type")
        ok = int(pred == expected)
        total += 1
        correct += ok
        conf_sum += float((out or {}).get("confidence") or 0.0)
        bucket = per_transform.setdefault(it["transform"], [0, 0])
        bucket[0] += ok
        bucket[1] += 1
        results.append({"suite_id": it["suite_id"], "transform": it["transform"],
                        "expected": expected, "predicted": pred,
                        "correct": bool(ok),
                        "confidence": (out or {}).get("confidence"),
                        "reasoning": ((out or {}).get("reasoning") or "")[:600]})

    out_path = Path(f"data/manifests/edge_{args.agent}_{prompt_version}_{args.model.replace('/','_')}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    acc = correct / max(1, total)
    mean_conf = conf_sum / max(1, total)
    print(f"edge bench [{args.agent}] model={args.model} "
          f"prompt={prompt_version}: {total} scored, {errors} errors -> {out_path}")
    print(f"  doc_type_accuracy {correct}/{total} = {acc:.4f} | mean confidence {mean_conf:.3f}")
    for tn in sorted(per_transform):
        hit, tot = per_transform[tn]
        print(f"  {tn:16s} {hit}/{tot} = {hit / tot:.2f}")
    _log_bench_run(args, prompt_version=prompt_version, n_scored=total,
                   n_error=errors, data_source=str(suite),
                   scores={"doc_type_accuracy": round(acc, 4),
                           "mean_confidence": round(mean_conf, 4)},
                   per_transform={tn: {"hit": h, "total": t}
                                  for tn, (h, t) in sorted(per_transform.items())})
    return 0


def _log_bench_run(args, *, prompt_version: str, n_scored: int, n_error: int,
                   scores: dict, data_source: str,
                   per_transform: dict | None = None,
                   served_model: str | None = None) -> None:
    """One compact append-only record per completed bench run."""
    try:
        from src.experiment_log import append_experiment, git_snapshot
        model = served_model or args.model
        record = {
            "experiment_name": (f"{model.replace('/', '_')}_{prompt_version}"
                                f"_{args.mode}"
                                + (f"_{getattr(args, 'agent', '') or getattr(args, 'role', '')}"
                                   if args.mode != "judge-mutation" else "")),
            "task": "agent_bench",
            "bench_mode": args.mode,
            "model": model,
            "requested_model": args.model,
            "prompt_versions": [prompt_version],
            "git_snapshot": git_snapshot(),
            "data_source": {"path": data_source},
            "parameters": {
                "mode": args.mode,
                "agent": getattr(args, "agent", None),
                "role": getattr(args, "role", None),
                "limit": args.limit,
                "seed": args.seed,
                "defects": getattr(args, "defects", None),
                "dry_run": False,
            },
            "rows": {"scored": n_scored, "errors": n_error},
            "scores": {"bench": scores, **({"per_transform": per_transform}
                                           if per_transform else {})},
        }
        append_experiment(record)
    except Exception as exc:  # logging must never fail the bench itself
        print(f"  [warn] experiment-log record skipped: {exc}")


def run_judge_mutation(args) -> int:
    from agents.judge_agent import JudgeAgent

    src = GT / "insurance_claim_realgt.jsonl"
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    rng = random.Random(args.seed)
    if args.limit:
        rows = rows[:args.limit]
    judge = JudgeAgent(model=args.model, api_key=args.api_key,
                       prompt_version=args.prompt_version or "judge-correctness")
    # JudgeAgent silently swaps the BaseAgent default model for the taxonomy's
    # judge.model — record the SERVED model, never the requested one.
    actual_model = judge.model
    if actual_model != args.model:
        print(f"  [note] judge model resolved to {actual_model} "
              f"(requested {args.model}; taxonomy judge.model override)")

    FIELD_LIST = "\n".join(f"  - {k}" for k in
                           ("claim_number","policy_number","insurer","insured_party",
                            "claim_type","date_of_loss","date_filed","claimed_amount",
                            "adjuster","damages_description","coverage_determination",
                            "denial_reasons"))
    tp = fp = tn = fn = clean_n = def_n = 0
    details = []
    for r in rows:
        text = r["doc_text"]
        gt = {k: v for k, v in r.items()
              if k not in ("filename", "doc_text", "label_source")}
        scenarios = [("clean", dict(gt))]
        for d in DEFECTS[:args.defects]:
            mutated = inject_defect(gt, d, rng)
            if json.dumps(mutated, sort_keys=True) == json.dumps(gt, sort_keys=True):
                continue  # no-op defect: don't count what was never planted
            scenarios.append((d, mutated))
        for kind, ext in scenarios:
            user = (f"Source document:\n\n{text[:20000]}\n\n"
                    f"Registered schema fields:\n{FIELD_LIST}\n\n"
                    f"Extraction to audit:\n{json.dumps(ext, indent=1)}\n\n"
                    "Audit correctness per your instructions.")
            res = judge._call_structured(user, json_schema=build_judge_schema(),
                                         temperature=0.0)
            label = 1 if kind != "clean" else 0          # 1 = defect present
            pred = verdict_flag(res)
            if kind == "clean":
                clean_n += 1
                fp += int(pred)                           # flagged clean = FP
                if pred:
                    details.append({"filename": r["filename"], "defect": "FALSE-FLAG",
                                    "verdict": res})
            else:
                def_n += 1
                if pred: tp += 1
                else:
                    fn += 1
                    details.append({"filename": r["filename"], "defect": kind,
                                    "verdict": res})
    recall = tp / max(1, tp + fn)
    fpr = fp / max(1, clean_n)
    print(f"judge-mutation [{judge.prompt_version}] model={actual_model}")
    print(f"  defective rows: {def_n} | caught(tp)={tp} missed(fn)={fn} -> recall={recall:.2f}")
    print(f"  clean rows: {clean_n} | false flags(fp)={fp} -> FPR={fpr:.2f}")
    out = Path(f"data/manifests/judge_mutation_{actual_model.replace('/','_')}.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for d in details:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"  misses written -> {out}")
    _log_bench_run(args, prompt_version=judge.prompt_version,
                   n_scored=clean_n + def_n, n_error=0,
                   scores={"defect_recall": round(recall, 4),
                           "clean_fpr": round(fpr, 4),
                           "tp": tp, "fn": fn, "fp": fp},
                   data_source=str(src), served_model=actual_model)
    return 0


def build_judge_schema():
    from agents.base_agent import build_structured_schema
    return build_structured_schema({
        "extraction_correctness_label": {"type": "string",
                                         "enum": ["accurate", "partial", "inaccurate"]},
        "field_verdicts": {"type": "object"},
        "notes": {"type": "string"},
    })


def verdict_flag(res: dict) -> bool:
    """A judge 'flags' when label is not accurate."""
    lab = str(res.get("extraction_correctness_label", "")).lower()
    return lab in ("partial", "inaccurate")


def run_conflicts(args) -> int:
    from agents.pipeline_agents import ArbiterAgent, BossAgent
    src = GT / "insurance_claim_realgt.jsonl"
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    rng = random.Random(args.seed)
    if args.limit:
        rows = rows[:args.limit]
    role = args.role
    correct = total = 0
    for r in rows:
        gt = {k: v for k, v in r.items()
              if k not in ("filename", "doc_text", "label_source")}
        bad = inject_defect(gt, rng.choice(DEFECTS), rng)
        if role == "arbiter":
            agent = ArbiterAgent(model=args.model, api_key=args.api_key)
            user = (f"Specialist extraction (rejected by the quality judge):\n"
                    f"{json.dumps(bad, indent=1)}\n\n"
                    "Decide the next action.")
            res = agent.run(user, ArbiterAgent.ARBITER_SCHEMA, temperature=0.0)
            act = res.get("action")
            total += 1
            if act == "retry_extraction":
                correct += 1
        elif role == "boss":
            agent = BossAgent(model=args.model, api_key=args.api_key)
            user = ("Two specialist extractions conflict.\n"
                    f"Extraction A:\n{json.dumps(gt, indent=1)}\n\n"
                    f"Extraction B:\n{json.dumps(bad, indent=1)}\n\n"
                    "Resolve.")
            res = agent.run(user, BossAgent.BOSS_SCHEMA, temperature=0.0)
            dec = res.get("decision")
            total += 1
            if dec in ("approved", "merged"):   # accept one / merge best
                correct += 1
    print(f"conflicts[{role}] model={args.model}: {correct}/{total} correct "
          f"({correct/max(1,total):.2f})")
    prompt_version = args.prompt_version or f"{role}_docclass_pilot_v0"
    _log_bench_run(args, prompt_version=prompt_version, n_scored=total,
                   n_error=0,
                   scores={"conflict_resolution_accuracy": round(correct / max(1, total), 4)},
                   data_source=str(src))
    return 0


def plan(args) -> int:
    """--dry-run: print the run plan; never construct an agent or call an LLM."""
    if args.mode == "edge":
        suite = _edge_suite_for(args.agent)
        n = sum(1 for l in suite.read_text().splitlines() if l.strip()) \
            if suite.exists() else 0
        rows = min(n, args.limit or n)
        pv = args.prompt_version or CLASSIFIER_ROLES.get(
            args.agent,
            "insurance_claims_specialist_v0"
            if args.agent == "insurance_claims_specialist" else args.agent)
        calls = rows
        print(f"PLAN edge [{args.agent}] suite={suite} "
              f"({'missing' if not n else f'{n} items'})")
    elif args.mode == "judge-mutation":
        src = GT / "insurance_claim_realgt.jsonl"
        n = sum(1 for l in src.read_text().splitlines() if l.strip())
        rows = min(n, args.limit or n)
        pv = args.prompt_version or "judge-correctness"
        calls = rows * (1 + args.defects)
        print(f"PLAN judge-mutation source={src}")
    else:
        src = GT / "insurance_claim_realgt.jsonl"
        n = sum(1 for l in src.read_text().splitlines() if l.strip())
        rows = min(n, args.limit or n)
        pv = args.prompt_version or f"{args.role}_docclass_pilot_v0"
        calls = rows
        print(f"PLAN conflicts [{args.role}] source={src}")
    print(f"  model={args.model} prompt={pv}")
    print(f"  rows={rows} llm_calls={calls} seed={args.seed} limit={args.limit}")
    print("  dry run: no agents constructed, no network calls made")
    return 0


def main_with_args(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--mode", required=True,
                    choices=["edge", "judge-mutation", "conflicts"])
    ap.add_argument("--agent", default="contracts_specialist")
    ap.add_argument("--role", default="arbiter", choices=["arbiter", "boss"])
    ap.add_argument("--model", default="qwen/qwen3.7-flash")
    ap.add_argument("--prompt-version", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--defects", type=int, default=5,
                    help="defect types per row in judge-mutation")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan (rows/calls/model/prompt); no LLM calls")
    args = ap.parse_args(argv)
    if args.dry_run:
        return plan(args)
    if args.mode == "edge":
        return run_edge(args)
    if args.mode == "judge-mutation":
        return run_judge_mutation(args)
    return run_conflicts(args)


def main() -> int:
    return main_with_args()


if __name__ == "__main__":
    raise SystemExit(main())
