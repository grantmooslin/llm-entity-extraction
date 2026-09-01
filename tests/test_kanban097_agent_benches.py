"""KANBAN-097: per-role eval tasks (agent bench suite) + mutation-iteration guards.

Guards:
1. NO-OP-MUTATION — every derived pilot variant DIFFERS from its base and
   embeds its lesson marker (the judge_correctness_docclass_pilot_v1 anchor
   drift shipped byte-identical bytes once; this pin makes that impossible
   to repeat silently).
2. REGISTRATION — every prompt version the bench references resolves through
   PROMPT_VERSIONS; the insurance_claims specialist schema/prompt wiring is
   coherent.
3. BENCH MECHANICS — classifier schema/message shape, defect injection
   determinism, verdict_flag semantics, dry-run plans (no network), and the
   compact append-only experiment-log record.

All network-free: agents are never constructed on the LLM path in these
tests; only plan()/schema/scoring helpers run.
"""

from __future__ import annotations

import json

import sys

sys.path.insert(0, ".")


# --------------------------------------------------------------------- 1

def test_derived_pilot_variants_are_not_noops():
    """A derived variant must differ from its base AND carry its lesson.

    Regression: judge_correctness_docclass_pilot_v1 originally replaced an
    anchor that did not exist in the base ('..._docclass_pilot_v0' — the
    authored marker reads '..._docclass_v0 (KANBAN-090).'), so str.replace()
    silently produced v0's exact bytes under a new registry key. Any A/B
    against such a 'variant' measures noise, not the lesson.
    """
    from src.prompts import PROMPT_VERSIONS

    v0 = PROMPT_VERSIONS["judge_correctness_docclass_pilot_v0"]
    v1 = PROMPT_VERSIONS["judge_correctness_docclass_pilot_v1"]
    assert v1 != v0, "pilot_v1 registered but byte-identical to v0 (no-op mutation)"
    # Head-prefix discipline: only the anchored tail region may differ.
    assert v1.startswith(v0[:300]), "head drift vs v0"
    # The lesson itself is present exactly once, with its own marker.
    assert v1.count("LABEL CONSISTENCY (mandatory)") == 1
    assert v1.count("judge_correctness_docclass_pilot_v1") >= 1
    # The stale marker must not survive into the variant.
    assert "judge_correctness_docclass_pilot_v0" not in v1
    # Exactly one strict-JSON closer survives (kanban090 closer discipline).
    assert v1.count("Output strict JSON only.") == 1


def test_insurance_specialist_v1_mutation_is_real_and_derived():
    """Mutation 1 (evidence-only visibility): differs from v0, keeps its head.

    Same regression class as the judge pilot_v1 no-op: a broken anchor would
    register identical bytes under a new key.
    """
    from src.prompts import PROMPT_VERSIONS

    v0 = PROMPT_VERSIONS["insurance_claims_specialist_v0"]
    v1 = PROMPT_VERSIONS["insurance_claims_specialist_v1"]
    assert v1 != v0, "v1 registered but byte-identical to v0"
    assert v1.startswith(v0[:400]), "head drift vs v0"
    assert v1.count("EVIDENCE-ONLY VISIBILITY") == 1
    assert "9a." in v1
    # Rule numbering intact: original rules 10 and 11 still present exactly once.
    assert v1.count("10. Return one complete JSON object") == 1
    assert v1.count("11. The `confidence` score") == 1


def test_all_bench_referenced_prompt_versions_registered():
    """Every default --prompt-version the bench can select MUST resolve."""
    from src.prompts import get_prompt
    from scripts.run_agent_bench import CLASSIFIER_ROLES, PILOT_CLASSES

    defaults = [
        *CLASSIFIER_ROLES.values(),
        "insurance_claims_specialist_v0",
        "judge-correctness",
        "judge_correctness_docclass_pilot_v0",
        "judge_correctness_docclass_pilot_v1",
        "arbiter_docclass_pilot_v0",
        "boss_docclass_pilot_v0",
        "reviewer_docclass_pilot_v0",
        "sorter_docclass_pilot_v3",
    ]
    for key in defaults:
        got = get_prompt(key)
        assert isinstance(got, str) and got.strip(), key
    # The pilot class list is exactly the GT universe the sorter suite spans.
    assert PILOT_CLASSES == ["contract", "corporate_record", "correspondence",
                             "insurance_claim", "merger_agreement"]


def test_insurance_specialist_schema_and_prompt_wiring():
    """The vendored specialist: schema registered, fields match its prompt."""
    from agents.specialist_agents import SPECIALIST_SCHEMAS, InsuranceClaimsSpecialist
    from src.prompts import get_prompt

    schema = SPECIALIST_SCHEMAS["insurance_claim"]
    props = schema["properties"]
    for field in ("claim_number", "policy_number", "insurer", "insured_party",
                  "claim_type", "date_of_loss", "date_filed", "claimed_amount",
                  "adjuster", "damages_description", "coverage_determination",
                  "denial_reasons", "supporting_documents"):
        assert field in props, field
    prompt = get_prompt("insurance_claims_specialist_v0")
    # The vendored base is prose-style rules; pin its load-bearing doctrine.
    for phrase in ("Claim and policy numbers", "never infer a determination",
                   "Output strict JSON" if "Output strict JSON" in prompt
                   else "one complete JSON object"):
        assert phrase in prompt, phrase
    agent = InsuranceClaimsSpecialist()
    assert agent.system_prompt() == prompt


# --------------------------------------------------------------------- 2

def test_classifier_schema_and_user_message():
    from scripts.run_agent_bench import PILOT_CLASSES, classifier_schema, classify_user_message

    schema = classifier_schema()
    enum = schema["properties"]["doc_type"]["enum"]
    assert sorted(enum) == sorted(PILOT_CLASSES)
    msg = classify_user_message("DOC BODY")
    for cls in PILOT_CLASSES:
        assert cls in msg
    assert "DOC BODY" in msg


def test_inject_defect_deterministic_and_mutating():
    import random

    from scripts.run_agent_bench import DEFECTS, inject_defect

    gt = {"filename": "f.txt", "effective_date": "2024-01-15",
          "denial_reasons": ["late filing"], "insurer": "ACME Insurance Co."}
    r1 = inject_defect(gt, "fabricate_entity", random.Random(42))
    r2 = inject_defect(gt, "fabricate_entity", random.Random(42))
    assert r1 == r2, "same inputs + same seed must give identical defects"
    assert r1["fabricated_party"] and r1["denial_reasons"] == gt["denial_reasons"]
    mutated = {d: inject_defect(gt, d, random.Random(42)) for d in DEFECTS}
    for d in ("swap_date", "drop_list_item", "wrong_amount", "null_where_present"):
        assert mutated[d] != gt, f"{d} failed to mutate"


def test_verdict_flag_semantics():
    from scripts.run_agent_bench import verdict_flag

    assert verdict_flag({"extraction_correctness_label": "accurate"}) is False
    assert verdict_flag({"extraction_correctness_label": "partial"}) is True
    assert verdict_flag({"extraction_correctness_label": "inaccurate"}) is True
    assert verdict_flag({}) is False


def test_dry_run_plans_never_construct_agents(capsys):
    """--dry-run prints the plan for all three modes without any LLM seam."""
    from scripts.run_agent_bench import main_with_args

    plans = [
        ["--mode", "edge", "--agent", "reviewer", "--limit", "5"],
        ["--mode", "edge", "--agent", "sorter", "--limit", "5"],
        ["--mode", "edge", "--agent", "contracts_specialist", "--limit", "5"],
        ["--mode", "judge-mutation", "--limit", "3"],
        ["--mode", "conflicts", "--role", "boss", "--limit", "3"],
        ["--mode", "conflicts", "--role", "arbiter", "--limit", "3"],
    ]
    for argv in plans:
        rc = main_with_args([*argv, "--dry-run"])
        assert rc == 0, argv
    out = capsys.readouterr().out
    assert out.count("dry run: no agents constructed") == len(plans)
    assert "llm_calls=" in out


def test_edge_suite_generator_is_deterministic(tmp_path, monkeypatch):
    """Same seed -> byte-identical suite; expectations stay machine-checkable."""
    import scripts.gen_edge_cases as gec

    monkeypatch.setattr(gec, "GT", tmp_path)
    monkeypatch.setattr(gec, "SUITES", tmp_path / "edge_suites")
    rows = {
        "filename": "sample.txt",
        "doc_text": "AGREEMENT between Party A and Party B. " * 40,
        "gt_fields": {"governing_law": "Delaware"},
    }
    s1 = gec.build_suite("contracts_specialist", [rows], per_doc=3, seed=42,
                         max_chars=40000, max_items=10)
    s2 = gec.build_suite("contracts_specialist", [rows], per_doc=3, seed=42,
                         max_chars=40000, max_items=10)
    assert s1 == s2 and s1, "deterministic rebuild expected"
    for item in s1:
        exp = item["expectations"]
        assert exp["no_fabrication"] is True
        assert set(exp) <= {"no_fabrication", "ignore_overlay", "all_optional_null",
                            "humility", "dedup_lists", "robust_values"}
        assert item["transform"] in gec.TRANSFORMS


def test_gt_workbench_catches_hallucinated_grounding(tmp_path, monkeypatch):
    """The workbench flags ungrounded verbatim families instead of trusting them."""
    import scripts.gt_workbench as gtw

    packets = tmp_path / "packets" / "contract"
    packets.mkdir(parents=True)
    body = "GOVERNING LAW. This Agreement is governed by the laws of Delaware. " * 6
    pkt = packets / "p1.txt"
    pkt.write_text(f"FILENAME: p1.pdf\n{'=' * 60}\n{body}", encoding="utf-8")
    good = {"filename": "p1.pdf", "governing_law": "Delaware"}
    bad = {"filename": "p1.pdf",
           "governing_law": "This Agreement is governed by the laws of Atlantis"}
    gt_file = tmp_path / "c_handgt.jsonl"
    gt_file.write_text(
        json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8")
    monkeypatch.setattr(gtw, "GT_DIR", tmp_path)
    monkeypatch.setattr(gtw, "PACKETS", tmp_path / "packets")
    n, errors = gtw.validate_file(gt_file, "contract", texts={})
    assert n == 2
    assert any("not grounded" in e for e in errors), errors


# --------------------------------------------------------------------- 3

def test_pipeline_role_wrappers_defaults_registered():
    from agents.pipeline_agents import (
        ArbiterAgent,
        BossAgent,
        ReviewerAgent,
        _StructuredAgent,
    )
    from src.prompts import get_prompt

    # BaseAgent's llm()/logging seam requires agent_name at CALL time —
    # regression: constructing the bare wrapper crashed only mid-bench.
    assert _StructuredAgent.agent_name
    bare = _StructuredAgent(prompt_version="reviewer_docclass_pilot_v0")
    assert bare.system_prompt() == get_prompt("reviewer_docclass_pilot_v0")
    assert get_prompt(ReviewerAgent().prompt_version)
    assert get_prompt(ArbiterAgent().prompt_version)
    assert get_prompt(BossAgent().prompt_version)
    assert {"decision"} <= set(BossAgent.BOSS_SCHEMA["properties"])
    assert {"action"} <= set(ArbiterAgent.ARBITER_SCHEMA["properties"])
    assert BossAgent.BOSS_SCHEMA["properties"]["decision"]["enum"] == [
        "approved", "merged", "review"]
    assert ArbiterAgent.ARBITER_SCHEMA["properties"]["action"]["enum"] == [
        "accept_with_caveats", "retry_extraction", "human_review"]


def test_bench_run_appends_one_experiment_record(tmp_path, monkeypatch, capsys):
    """Completed bench runs land ONE compact record in the canonical log."""
    from scripts import run_agent_bench as rab

    log = tmp_path / "experiment_log.jsonl"
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(log))
    ns = rab.argparse.Namespace(
        mode="conflicts", agent="x", role="boss", model="test/model",
        prompt_version=None, api_key=None, limit=7, seed=42, defects=5,
        max_tokens=16000, dry_run=False)
    rab._log_bench_run(ns, prompt_version="boss_docclass_pilot_v0",
                       n_scored=7, n_error=0,
                       scores={"conflict_resolution_accuracy": 0.8571},
                       data_source="data/gt/insurance_claim_realgt.jsonl")
    lines = [l for l in log.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["task"] == "agent_bench"
    assert rec["bench_mode"] == "conflicts"
    assert rec["scores"]["bench"] == {"conflict_resolution_accuracy": 0.8571}
    assert rec["parameters"]["limit"] == 7
    assert "git_snapshot" in rec
