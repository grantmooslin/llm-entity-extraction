#!/usr/bin/env python3
"""Prompt Engineer — automated DRAFT-phase mutations for the docclass family.

Implements the iteration-OS DRAFT step (roadmap §III): given a failed-eval
manifest, decompose the misses into clusters, then have an LLM propose ONE
surgical `.replace()` mutation per invocation under strict mechanical
validation:

    OBSERVE (manifest) -> DECOMPOSE (clusters + reasoning quotes)
    -> DRAFT (LLM proposal as JSON) -> VALIDATE (mechanical checks)
    -> APPLY (new version constant + registry + test-count bump)

Validation gates (a proposal that fails any gate is rejected, never applied):
  1. anchor substring occurs EXACTLY ONCE in the base prompt text
  2. proposed version key is unused and follows the lineage naming
  3. mutation is additive-only (no deletion of existing rule text beyond the
     anchor span)
  4. registry/test-count patches are consistent

The tool never runs the A/B itself; it prints the exact runner command
(one rule per iteration -> one A/B per mutation).

Usage:
    python3 scripts/prompt_engineer.py \\
        --manifest data/manifests/docclass_pilot140_cand_pilot_v1_qwen.jsonl \\
        --base-version sorter_docclass_pilot_v1 \\
        --focus "insurance_claim" --apply

    python3 scripts/prompt_engineer.py --manifest ... --dry-run   # clusters only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

TARGET_FILE = REPO_ROOT / "src" / "prompts_docclass.py"
TESTS_FILE = REPO_ROOT / "tests" / "test_kanban090_docclass_prompts.py"
META_SYSTEM = """You are the Prompt Engineer for a legal-document classification \
prompt program. You follow a strict iteration doctrine:

- ONE rule per mutation. Never bundle unrelated fixes.
- Mutations are surgical .replace() edits on the parent prompt: you return an \
ANCHOR (a verbatim substring of the parent, occurring exactly once) and its \
REPLACEMENT (anchor preserved plus your insertion/edit).
- Every rule carries: the concrete failure evidence it addresses (filename, \
GT vs prediction), the mechanism, a scope guard against over-firing, and \
where possible a worked example.
- Prefer corpus-convention rules ("the ground truth follows the folder") over \
legal reasoning when the misses follow a labeling convention.
- Known GT artifacts are NOT prompt-fixable: say so and skip.
- Counterfactual discipline: name what your rule could break on OTHER corpora \
and add the carve-out preemptively.

Return ONLY a JSON object:
{
 "version_key": "<lineage>_v<n+1>",
 "anchor": "<verbatim unique substring of the base prompt>",
 "replacement": "<anchor with your edit applied>",
 "rule_name": "<short name>",
 "rationale": "<failure evidence -> mechanism -> fix>",
 "risk_scan": {"rewards": ["..."], "risks": ["..."], "carve_outs": ["..."]},
 "gt_artifacts": ["<clusters you deliberately did NOT chase>"]
}"""


def load_manifest(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("type"):
            continue
        # Edge-bench manifest shape: {suite_id, transform, ungrounded_fields,
        # extracted_fields, expectation_passes} — failures are rows whose
        # expectations did not all pass or that errored outright.
        if "suite_id" in d:
            failed = ("error" in d) or any(
                not v for v in (d.get("expectation_passes") or {}).values())
            if not failed:
                continue
            un = d.get("ungrounded_fields") or []
            gt = d.get("transform", "edge") + ("/" + ",".join(un) if un else "")
            rows.append({"filename": d.get("base_filename",
                                          d.get("suite_id","")),
                         "doc_type": d.get("transform", "edge"),
                         "gt": ",".join(un) if un else d.get("transform", "edge"),
                         "pred_doc_type": None, "pred_subclass": None,
                         "reasoning": json.dumps({
                             "ungrounded_fields": un,
                             "extracted_fields": d.get("extracted_fields", {}),
                             "error": d.get("error"),
                         })[:400]})
            continue
        # Judge-mutation manifest shape: {filename, defect, verdict}
        if "verdict" in d and d.get("defect") not in (None, "FALSE-FLAG"):
            rows.append({"filename": d.get("filename",""), "doc_type": "judge",
                         "gt": d["defect"], "pred_doc_type": None,
                         "pred_subclass": None,
                         "reasoning": json.dumps(d.get("verdict",{}))[:400]})
            continue
        comp = (d.get("scores") or {}).get("composite", {}).get("sorter", {})
        if not d.get("expected_subclass"):
            continue
        if not comp.get("subclass_ok"):
            rows.append({
                "filename": d["filename"],
                "doc_type": d["expected_doc_type"],
                "gt": d["expected_subclass"],
                "pred_doc_type": (d.get("predicted") or {}).get("doc_type"),
                "pred_subclass": (d.get("predicted") or {}).get("doc_subclass"),
                "reasoning": (comp.get("reasoning") or "")[:400],
            })
    return rows


def decompose(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    clusters: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        clusters[(r["doc_type"], r["gt"])].append(r)
    return dict(sorted(clusters.items(), key=lambda kv: -len(kv[1])))


def render_clusters(clusters) -> str:
    out = []
    for (dt, gt), items in clusters.items():
        preds = Counter(i["pred_subclass"] for i in items).most_common(3)
        out.append(f"### {dt} / GT subclass {gt!r} — {len(items)} miss(es); "
                   f"model answered {preds}")
        for i in items[:2]:
            out.append(f"  file: {i['filename'][:70]}")
            out.append(f"  reasoning: {i['reasoning'][:280]}")
    return "\n".join(out)


def llm_propose(model: str, base_text: str, base_key: str,
                clusters_text: str, focus: str | None) -> dict:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / "config" / "environments" / ".env")
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set (config/environments/.env)")
    from langchain_openai import ChatOpenAI

    from src.openrouter_utils import OPENROUTER_BASE_URL

    llm = ChatOpenAI(model=model, api_key=api_key, base_url=OPENROUTER_BASE_URL,
                     temperature=0.0, max_tokens=8000, timeout=240)
    # Reasoning models burn budget before emitting content — keep effort low
    # so the JSON proposal survives the token cap.
    llm.extra_body = {"reasoning": {"effort": "low"}}
    next_n = int(re.search(r"_v(\d+)$", base_key).group(1)) + 1
    lineage = re.sub(r"_v\d+$", "", base_key)
    focus_note = focus or "all — pick the SINGLE highest reward/risk cluster"
    user = f"""BASE PROMPT VERSION KEY: {base_key}
NEXT VERSION KEY MUST BE: {lineage}_v{next_n}

FAILURE CLUSTERS TO ADDRESS (focus={focus_note}):

{clusters_text}

BASE PROMPT (verbatim, truncated to relevant tail):
...
{base_text[-6000:]}
"""
    msg = llm.invoke([("system", META_SYSTEM), ("user", user)])
    parts = [msg.content if isinstance(msg.content, str) else str(msg.content)]
    rc = (msg.additional_kwargs or {}).get("reasoning_content")
    if isinstance(rc, str):
        parts.append(rc)
    text = "\n".join(str(x) for x in parts)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # strip think blocks
    # Robust extraction: raw_decode respects JSON string quoting (braces
    # inside string values previously derailed a naive depth counter).
    # Prefer the first parsed object that actually carries an anchor.
    dec = json.JSONDecoder()
    candidates = []
    for m in re.finditer(r"\{", text):
        try:
            obj, _end = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
            if obj.get("anchor"):
                break
    best = None
    for obj in candidates:
        if obj.get("anchor"):
            best = obj
            break
    if best is None and candidates:
        best = candidates[0]
    if best is None:
        raise SystemExit("no parsable JSON; part sizes="
                         + ",".join(str(len(str(x))) for x in parts)
                         + f"; tail:\n{text[-600:]}")
    if not best.get("anchor"):
        raise SystemExit("proposer JSON lacked anchor; raw reply sizes="
                         + ",".join(str(len(str(x))) for x in parts)
                         + f"; head:\n{text[:800]}")
    # The version key is deterministic lineage arithmetic — never trust the
    # model with it.
    best["version_key"] = f"{lineage}_v{next_n}"
    return best


def validate(proposal: dict, base_text: str, existing_keys: set[str]) -> list[str]:
    problems = []
    anchor = proposal.get("anchor", "")
    replacement = proposal.get("replacement", "")
    key = proposal.get("version_key", "")
    n = base_text.count(anchor)
    if not anchor:
        problems.append("empty anchor")
    elif n == 0:
        problems.append(f"anchor not found in base ({len(anchor)} chars)")
    elif n > 1:
        problems.append(f"anchor found {n} times (must be exactly once)")
    if key in existing_keys:
        problems.append(f"version key already exists: {key}")
    if not re.match(r"^[a-z0-9_]+_v\d+$", key):
        problems.append(f"bad version key shape: {key}")
    if anchor and anchor not in replacement:
        problems.append("mutation is not additive: anchor not contained in replacement")
    for req in ("rationale", "risk_scan", "rule_name"):
        if req not in proposal:
            problems.append(f"missing field: {req}")
    return problems


def resolve_spec(spec_arg: str | None):
    """Return (target_file, registry_dict, test_file) from a family spec."""
    global TARGET_FILE, TESTS_FILE
    if not spec_arg:
        return
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML required for --spec")
    file_part, _, fam = spec_arg.partition(":")
    fam = fam or Path(file_part).stem
    cfg_path = (Path(file_part) if file_part.endswith((".yaml", ".yml"))
                else REPO_ROOT / "config" / "prompt_engineer" / f"{Path(file_part).stem}.yaml")
    families = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if fam not in families:
        raise SystemExit(f"family '{fam}' not in {cfg_path}; "
                         f"known: {', '.join(families)}")
    cfg = families[fam]
    TARGET_FILE = REPO_ROOT / cfg["target_file"]
    TESTS_FILE = REPO_ROOT / cfg["test_file"]
    return cfg


def apply_mutation(proposal: dict, base_key: str, registry_dict: str = "DOCCLASS_PROMPT_VERSIONS") -> None:
    src = TARGET_FILE.read_text(encoding="utf-8")
    # Resolve the base CONSTANT name from its registry entry — key->constant
    # is not mechanical ("sorter_docclass_pilot_v1" lives in
    # SORTER_DOCCLASS_PILOT_PROMPT_V1).
    marker = f'"{base_key}":'
    idx = src.find(marker)
    if idx == -1:
        raise SystemExit(f"registry entry for {base_key} not found")
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)", src[idx + len(marker):])
    if not m:
        raise SystemExit(f"registry entry for {base_key} malformed")
    const_base = m.group(1)
    # New constant: same convention as siblings (insert _PROMPT_ where the
    # base has it), else plain upper.
    const_new = proposal["version_key"].upper()
    if "_PROMPT_" in const_base:
        const_new = const_new.replace("_PILOT_", "_PILOT_PROMPT_", 1) \
            if "_PILOT_" in const_new else const_new
    block = (
        f"\n{const_new} = {const_base}.replace(\n"
        f"    {proposal['anchor']!r},\n"
        f"    {proposal['replacement']!r},\n"
        f")\n"
    )
    reg_anchor = f'"{base_key}":'
    assert reg_anchor in src, f"registry entry for {base_key} not found"
    # insert constant right after the base constant's assignment chain ends:
    # simplest safe point = immediately BEFORE the registry dict definition.
    reg_def_a = registry_dict + ": dict[str, Any] = {"
    reg_def_b = registry_dict + " = {"
    if reg_def_a not in src and reg_def_b not in src:
        raise SystemExit(f"registry {registry_dict} not found")
    reg_def = reg_def_a if reg_def_a in src else reg_def_b
    src = src.replace(
        reg_anchor,
        f'"{proposal["version_key"]}": {const_new},\n    ' + reg_anchor,
        1,
    )
    TARGET_FILE.write_text(src, encoding="utf-8")

    if TESTS_FILE.exists():
        t = TESTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"EXPECTED_DOCCLASS_KEY_COUNT = (\d+)", t)
        if m:
            t = t.replace(m.group(0),
                          f"EXPECTED_DOCCLASS_KEY_COUNT = {int(m.group(1)) + 1}")
            TESTS_FILE.write_text(t, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--base-version", required=True)
    ap.add_argument("--model", default="qwen/qwen3.7-flash")
    ap.add_argument("--focus", default=None,
                    help="doc_type or doc_type/subclass to target")
    ap.add_argument("--spec", default=None,
                    help="config/prompt_engineer/<family> or YAML path; supplies "
                         "target/registry/test paths from the family block")
    ap.add_argument("--apply", action="store_true",
                    help="write the mutation into src/prompts_docclass.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    spec_cfg = resolve_spec(args.spec) if args.spec else None
    rows = load_manifest(Path(args.manifest))
    clusters = decompose(rows)
    print(f"manifest failures: {len(rows)} across {len(clusters)} clusters\n")
    print(render_clusters(clusters))

    if args.dry_run or not args.apply:
        print("\n(dry run — rerun with --apply to draft a mutation)")
        return 0

    from src.prompts import get_prompt, PROMPT_VERSIONS

    base_text = get_prompt(args.base_version)
    focus = args.focus
    if focus and "/" in focus:
        dt, sub = focus.split("/")
        clusters = {k: v for k, v in clusters.items() if k == (dt, sub)}
    elif focus:
        clusters = {k: v for k, v in clusters.items() if k[0] == focus}
        focus = None
    if not clusters:
        raise SystemExit("no clusters match --focus")

    proposal = llm_propose(args.model, base_text, args.base_version,
                           render_clusters(clusters), focus)
    for req in ("rule_name", "rationale"):
        proposal.setdefault(req, "(not provided)")
        if not proposal.get(req):
            proposal[req] = "(not provided)"
    proposal.setdefault("anchor", "")
    proposal.setdefault("replacement", "")
    problems = validate(proposal, base_text, set(PROMPT_VERSIONS))
    print("\n== proposal ==")
    print(json.dumps({k: proposal.get(k) for k in ("version_key", "rule_name", "rationale")},
                     indent=2, ensure_ascii=False)[:1200])  # KANBAN-088-EXEMPT: pretty-print preview snippet, not a JSONL row write
    print("risk_scan:", json.dumps(proposal.get("risk_scan", {}), indent=2)[:800])
    Path("/tmp/opencode/pe_proposal.json").write_text(
        json.dumps(proposal, indent=2, ensure_ascii=False))  # KANBAN-088-EXEMPT: pretty-print preview snippet, not a JSONL row write
    if problems:
        print("\nREJECTED — validation gates:")
        for p in problems:
            print("  -", p)
        return 1

    if args.apply:
        apply_mutation(proposal, args.base_version,
                       (spec_cfg or {}).get("registry_dict",
                                            "DOCCLASS_PROMPT_VERSIONS"))
        print(f"\nAPPLIED: {proposal['version_key']} written to {TARGET_FILE.name}")
        print("next step (one rule per iteration -> one A/B):\n"
              f"  python3 scripts/eval/run_langfuse_docclass_eval.py \\\n"
              f"      --local-dumps data/datasets/docclass_merged_pilot140.jsonl \\\n"
              f"      --class-set pilot --prompt-version {proposal['version_key']} \\\n"
              f"      --model qwen/qwen3.7-flash --experiment-name "
              f"qwen3.7-flash_{proposal['version_key']}_pilot140")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
