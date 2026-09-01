"""KANBAN-090: dedicated docclass prompt variants for every chain role.

Guards three things:
1. REGISTRATION — every DOCCLASS_PROMPT_VERSIONS key resolves through
   get_prompt()/PROMPT_VERSIONS (registration IS deployment: the Langfuse
   sync mirrors every registered version).
2. DERIVATION — derived variants keep the repo's append-only discipline
   (head-prefix off the real base, single JSON closer, KANBAN-090 marker);
   authored-fresh V0s carry provenance markers instead.
3. DEFAULT-UNCHANGED — no runtime route changed: generic keys never contain
   the docclass context block.
"""

EXPECTED_DOCCLASS_KEY_COUNT = 58  # 32 KANBAN-090 + 22 KANBAN-101 + 4 KANBAN-103


def _doc():
    import sys

    sys.path.insert(0, ".")
    from src.prompts_docclass import DOCCLASS_PROMPT_VERSIONS

    return DOCCLASS_PROMPT_VERSIONS


def test_registry_complete_and_resolvable():
    from src.prompts import PROMPT_VERSIONS, get_prompt

    reg = _doc()
    assert len(reg) == EXPECTED_DOCCLASS_KEY_COUNT
    for key in reg:
        assert key in PROMPT_VERSIONS, f"unregistered: {key}"
        assert get_prompt(key) == reg[key]
    # The 13 genuinely new keys (sorter family pre-dated this card).
    new_keys = [
        "contracts_specialist_docclass_v0",
        "corporate_records_specialist_docclass_v0",
        "due_diligence_specialist_docclass_v0",
        "correspondence_specialist_docclass_v0",
        "compliance_specialist_docclass_v0",
        "court_opinions_specialist_docclass_v0",
        "insurance_claims_specialist_docclass_v0",
        "reviewer_docclass_v0",
        "arbiter_docclass_v0",
        "judge_docclass_v0",
        "judge_classification_docclass_v0",
        "judge_correctness_docclass_v0",
        "boss_docclass_v0",
    ]
    assert all(k in PROMPT_VERSIONS for k in new_keys)


def test_sorter_family_is_reexported_byte_identical():
    import sys

    sys.path.insert(0, ".")
    from src import prompts as P
    from src.prompts_docclass import DOCCLASS_PROMPT_VERSIONS

    for mod_name, key in [
        ("SORTER_DOCCLASS_PROMPT_V0", "sorter_docclass_v0"),
        ("SORTER_DOCCLASS_PROMPT_V3", "sorter_docclass_v3"),
        ("SORTER_DOCCLASS_PROMPT_V6", "sorter_docclass_v6"),
        ("SORTER_DOCCLASS_PROMPT_V7", "sorter_docclass_v7"),
        ("SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V0", "sorter_docclass_correspondence_v0"),
        ("SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V1", "sorter_docclass_correspondence_v1"),
        ("SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V2", "sorter_docclass_correspondence_v2"),
        ("SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V3", "sorter_docclass_correspondence_v3"),
        ("SORTER_DOCCLASS_VISION_PROMPT_V0", "sorter_docclass_vision_v0"),
        ("SORTER_DOCCLASS_VISION_PROMPT_V1", "sorter_docclass_vision_v1"),
    ]:
        # Same OBJECT, not just equal bytes — a re-export, never a redefinition.
        assert DOCCLASS_PROMPT_VERSIONS[key] is getattr(P, mod_name), key


def test_derived_variants_keep_append_only_discipline():
    import sys

    sys.path.insert(0, ".")
    from src import prompts as P
    from src.prompts_docclass import DOCCLASS_PROMPT_VERSIONS

    pairs = [
        ("contracts_specialist_docclass_v0", P.CONTRACTS_SPECIALIST_PROMPT),
        ("corporate_records_specialist_docclass_v0", P.CORPORATE_RECORDS_SPECIALIST_PROMPT),
        ("due_diligence_specialist_docclass_v0", P.DUE_DILIGENCE_SPECIALIST_PROMPT),
        ("correspondence_specialist_docclass_v0", P.CORRESPONDENCE_SPECIALIST_PROMPT),
        ("compliance_specialist_docclass_v0", P.COMPLIANCE_SPECIALIST_PROMPT),
        ("court_opinions_specialist_docclass_v0", P.COURT_OPINIONS_SPECIALIST_PROMPT),
        ("boss_docclass_v0", P.BOSS_SYSTEM_PROMPT),
        ("judge_docclass_v0", P.JUDGE_SYSTEM_PROMPT),
        ("judge_classification_docclass_v0", P.CLASSIFICATION_SYSTEM_PROMPT),
        ("judge_correctness_docclass_v0", P.CORRECTNESS_SYSTEM_PROMPT),
    ]
    for key, base in pairs:
        variant = DOCCLASS_PROMPT_VERSIONS[key]
        # House pattern (cf. sorter v7..v15 lineage tests): head-prefix.
        assert variant.startswith(base[:300]), f"head drift: {key}"
        assert variant != base, f"variant equals base: {key}"
        # Append-only: everything after the insertion point is base tail.
        assert variant.endswith(base[-200:]) or variant.count(
            "Output strict JSON only."
        ) >= base.count("Output strict JSON only."), f"tail drift: {key}"
        # Exactly ONE strict-JSON closer survives (no duplicated block).
        assert variant.count("Output strict JSON only.") == 1, key
        assert "(KANBAN-090)" in variant, key
        assert "DOCCLASS ARM CONTEXT" in variant, key


def test_anchor_guards_future_base_edits():
    """If a future card edits a base prompt and adds a second JSON closer,
    the derivation replace would duplicate the block — fail loudly here."""
    import sys

    sys.path.insert(0, ".")
    from src import prompts as P

    bases = [
        P.CONTRACTS_SPECIALIST_PROMPT,
        P.CORPORATE_RECORDS_SPECIALIST_PROMPT,
        P.DUE_DILIGENCE_SPECIALIST_PROMPT,
        P.CORRESPONDENCE_SPECIALIST_PROMPT,
        P.COMPLIANCE_SPECIALIST_PROMPT,
        P.COURT_OPINIONS_SPECIALIST_PROMPT,
        P.BOSS_SYSTEM_PROMPT,
        P.JUDGE_SYSTEM_PROMPT,
        P.CLASSIFICATION_SYSTEM_PROMPT,
        P.CORRECTNESS_SYSTEM_PROMPT,
    ]
    for i, b in enumerate(bases):
        assert b.count("Output strict JSON only.") == 1, f"base[{i}] anchor drift"


def test_authored_fresh_v0s_carry_provenance_and_schema():
    from src.prompts_docclass import (
        ARBITER_DOCCLASS_PROMPT_V0,
        INSURANCE_CLAIMS_SPECIALIST_DOCCLASS_PROMPT_V0,
        REVIEWER_DOCCLASS_PROMPT_V0,
    )

    for p in (
        REVIEWER_DOCCLASS_PROMPT_V0,
        ARBITER_DOCCLASS_PROMPT_V0,
        INSURANCE_CLAIMS_SPECIALIST_DOCCLASS_PROMPT_V0,
    ):
        assert "(KANBAN-090)" in p
        assert "DOCCLASS ARM CONTEXT" in p or "docclass" in p.lower()
    # Provenance lives as module comments next to each authored constant.
    from pathlib import Path

    module_src = (
        Path(__file__).resolve().parent.parent / "src" / "prompts_docclass.py"
    ).read_text()
    for const in (
        "REVIEWER_DOCCLASS_PROMPT_V0",
        "ARBITER_DOCCLASS_PROMPT_V0",
        "INSURANCE_CLAIMS_SPECIALIST_DOCCLASS_PROMPT_V0",
    ):
        idx = module_src.index(f"{const} = ")
        head = module_src[max(0, idx - 600) : idx]
        assert "llm-mailroom" in head, f"provenance comment missing above {const}"
    # Extended class set named in reviewer + arbiter.
    for p in (REVIEWER_DOCCLASS_PROMPT_V0, ARBITER_DOCCLASS_PROMPT_V0):
        for cls in (
            "insurance_claim",
            "merger_agreement",
            "corporate_record",
            "court_opinion",
        ):
            assert cls in p, f"{cls} missing"
    # Insurance specialist carries its claims-native schema fields.
    for field in (
        "claim_number",
        "policy_number",
        "coverage_determination",
        "denial_reasons",
    ):
        assert field in INSURANCE_CLAIMS_SPECIALIST_DOCCLASS_PROMPT_V0


def test_v1_variants_carry_kanban101_markers():
    from src.prompts_docclass import DOCCLASS_PROMPT_VERSIONS

    kanban101_keys = [
        "contracts_specialist_docclass_v1",
        "corporate_records_specialist_docclass_v1",
        "due_diligence_specialist_docclass_v1",
        "correspondence_specialist_docclass_v1",
        "compliance_specialist_docclass_v1",
        "court_opinions_specialist_docclass_v1",
        "insurance_claims_specialist_docclass_v1",
        "reviewer_docclass_v1",
        "arbiter_docclass_v1",
        "boss_docclass_v1",
        "judge_docclass_v1",
        "judge_classification_docclass_v1",
        "judge_correctness_docclass_v1",
    ]
    for key in kanban101_keys:
        assert key in DOCCLASS_PROMPT_VERSIONS
        assert "(KANBAN-101)" in DOCCLASS_PROMPT_VERSIONS[key], key


def test_pilot_specialist_variants_present():
    from src.prompts_docclass import DOCCLASS_PROMPT_VERSIONS

    for key in (
        "contracts_specialist_docclass_pilot_v0",
        "corporate_records_specialist_docclass_pilot_v0",
        "due_diligence_specialist_docclass_pilot_v0",
        "correspondence_specialist_docclass_pilot_v0",
        "compliance_specialist_docclass_pilot_v0",
        "court_opinions_specialist_docclass_pilot_v0",
        "insurance_claims_specialist_docclass_pilot_v0",
    ):
        assert key in DOCCLASS_PROMPT_VERSIONS
        assert "pilot" in DOCCLASS_PROMPT_VERSIONS[key].lower() or "PILOT" in DOCCLASS_PROMPT_VERSIONS[key]


def test_runtime_defaults_untouched():
    """Nothing fetches a docclass key by default: generic routes unchanged."""
    import sys

    sys.path.insert(0, ".")
    from src import prompts as P
    from src.prompts import get_prompt

    assert get_prompt("sorter") == P.PROMPT_VERSIONS["sorter"]
    assert "DOCCLASS ARM CONTEXT" not in get_prompt("sorter")
    assert "DOCCLASS ARM CONTEXT" not in get_prompt("contracts_specialist")
    assert "DOCCLASS ARM CONTEXT" not in get_prompt("boss")
    assert "DOCCLASS ARM CONTEXT" not in get_prompt("judge")
    # Generic specialist keys still resolve to the SAME objects as before.
    assert get_prompt("contracts_specialist") is P.CONTRACTS_SPECIALIST_PROMPT
