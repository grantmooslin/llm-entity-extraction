"""Tests for the versioned prompt registry."""

import pytest

from src.prompts import (
    DEFAULT_PROMPT_VERSION,
    PROMPT_TEMPLATES,
    PROMPT_VERSIONS,
    get_prompt,
    list_prompts,
)


def test_all_prompt_keys_exist():
    assert "sorter" in PROMPT_VERSIONS
    assert "sorter_v0" in PROMPT_VERSIONS
    assert "sorter_v1" in PROMPT_VERSIONS
    assert "sorter_v2" in PROMPT_VERSIONS
    assert "contracts_specialist" in PROMPT_VERSIONS
    assert "contracts_specialist_v1" in PROMPT_VERSIONS
    assert "contracts_specialist_v2" in PROMPT_VERSIONS
    assert "contracts_specialist_v3" in PROMPT_VERSIONS
    assert "contracts_specialist_v4" in PROMPT_VERSIONS
    assert "contracts_specialist_v5" in PROMPT_VERSIONS
    assert "corporate_records_specialist" in PROMPT_VERSIONS
    assert "due_diligence_specialist" in PROMPT_VERSIONS
    assert "correspondence_specialist" in PROMPT_VERSIONS
    assert "compliance_specialist" in PROMPT_VERSIONS
    assert "court_opinions_specialist" in PROMPT_VERSIONS
    assert "judge" in PROMPT_VERSIONS
    assert "judge-classification" in PROMPT_VERSIONS
    assert "judge-correctness" in PROMPT_VERSIONS
    assert "boss" in PROMPT_VERSIONS
    assert "reporter" in PROMPT_VERSIONS


def test_contracts_archive_preserves_identity_and_version_keys():
    """The v1..v16 lineage lives in src/prompts_archive.py (frozen) but every
    version key must stay resolvable and the constants byte-identical.

    The version key IS the experiment identity — manifests, the experiment
    log, `get_prompt()`, and Langfuse prompt syncs reference these versions.
    The archive keeps the editing surface of src/prompts.py lean (the
    pre-documentation v1..v16 full-text + early replace chain is ~1,000
    lines) without ever mutating a prompt string.
    """
    import src.prompts as prompts_module
    import src.prompts_archive as archive

    # Every archived constant is a non-empty string, resolvable through the
    # registry, and byte-identical to the constant re-exported by prompts.py.
    for i in range(1, 17):
        name = f"CONTRACTS_SPECIALIST_PROMPT_V{i}"
        arch = getattr(archive, name)
        assert isinstance(arch, str) and len(arch) > 1000, name
        assert arch == getattr(prompts_module, name), name
        assert PROMPT_VERSIONS[f"contracts_specialist_v{i}"] == arch, name


def test_contracts_archive_chain_heads_resolve():
    """The v17+ replace chain derives from V16 — after the archive move the
    chain still resolves end-to-end and each head is strictly derived."""
    from src.prompts import CONTRACTS_SPECIALIST_PROMPT_V16, CONTRACTS_SPECIALIST_PROMPT_V32

    assert CONTRACTS_SPECIALIST_PROMPT_V32 != CONTRACTS_SPECIALIST_PROMPT_V16
    assert CONTRACTS_SPECIALIST_PROMPT_V32.startswith(CONTRACTS_SPECIALIST_PROMPT_V16[:300])
    assert PROMPT_VERSIONS["contracts_specialist_v32"] == CONTRACTS_SPECIALIST_PROMPT_V32


def test_sorter_v2_hybrid_and_endorsement_rules():
    prompt = get_prompt("sorter_v2")
    assert "HYBRID AGREEMENTS" in prompt
    assert "SUBTYPE CONFIDENCE" in prompt
    # The endorsement description (injected via {{contract_subtypes}}) is
    # broadened beyond celebrity deals to include product/insurance riders.
    from agents.sorter_agent import SorterAgent

    rendered = SorterAgent(prompt_version="sorter_v2").system_prompt()
    assert "endorsement riders" in rendered
    assert "{{contract_subtypes}}" in prompt


def test_extractor_v5_truncation_and_full_clause_rules():
    prompt = get_prompt("contracts_specialist_v5")
    assert "TRUNCATION-AWARE COMPLETENESS" in prompt
    assert "ninety (90) days" in prompt  # full termination clause incl. riders
    assert "Governing Law" in prompt
    # v5 keeps v4's Yes/No category enumeration.
    assert "anti-assignment" in prompt
    assert "third-party beneficiary" in prompt


def test_sorter_v7_data_backed_rules():
    from src.prompts import SORTER_PROMPT_V6, SORTER_PROMPT_V7

    # v7 is a strict derivation of v6: the base is untouched, the derived
    # prompt adds the three rules for the v6 509-doc confusion clusters.
    assert SORTER_PROMPT_V7 != SORTER_PROMPT_V6
    assert SORTER_PROMPT_V7.startswith(SORTER_PROMPT_V6[:300])
    assert "sorter_v7" in PROMPT_VERSIONS

    v7 = SORTER_PROMPT_V7
    assert "18. CONSORTIUM O&M IS MAINTENANCE" in v7
    assert "submarine-cable consortium" in v7
    assert "19. DEVELOPMENT OVER LICENSE" in v7
    assert "delivery mechanism for developed products" in v7
    assert "20. PROMOTION GUARD" in v7
    assert "not marketing and not distributor" in v7
    # The option list is intact and the rule set ends before it.
    assert "VALID CONTRACT SUBTYPE KEYS" in v7
    # v6 predates the three rules.
    assert "CONSORTIUM O&M IS MAINTENANCE" not in SORTER_PROMPT_V6
    assert "PROMOTION GUARD" not in SORTER_PROMPT_V6


def test_sorter_v8_remaining_clusters():
    from src.prompts import SORTER_PROMPT_V7, SORTER_PROMPT_V8

    # v8 is a strict derivation of v7: the base is untouched, the derived
    # prompt adds the two rules for the v7 243-doc residual clusters.
    assert SORTER_PROMPT_V8 != SORTER_PROMPT_V7
    assert SORTER_PROMPT_V8.startswith(SORTER_PROMPT_V7[:300])
    assert "sorter_v8" in PROMPT_VERSIONS

    v8 = SORTER_PROMPT_V8
    assert "21. DEVELOPMENT VERSUS COLLABORATION, LICENSE, AND FRANCHISE STRUCTURES" in v8
    assert "Collaborative Development and Commercialization Agreement" in v8
    assert "Franchise Development Agreement" in v8
    assert "22. INTELLECTUAL PROPERTY AGREEMENTS ARE ip" in v8
    assert "not route them to license or to joint_venture" in v8
    assert "VALID CONTRACT SUBTYPE KEYS" in v8
    # v7 predates the two rules.
    assert "21. DEVELOPMENT VERSUS COLLABORATION" not in SORTER_PROMPT_V7
    assert "INTELLECTUAL PROPERTY AGREEMENTS ARE ip" not in SORTER_PROMPT_V7


def test_sorter_v9_title_wins_rules():
    from src.prompts import SORTER_PROMPT_V8, SORTER_PROMPT_V9

    # v9 is a strict derivation of v8: the base is untouched, the derived
    # prompt adds the three title-vs-machinery rules for the v8 residuals.
    assert SORTER_PROMPT_V9 != SORTER_PROMPT_V8
    assert SORTER_PROMPT_V9.startswith(SORTER_PROMPT_V8[:300])
    assert "sorter_v9" in PROMPT_VERSIONS

    v9 = SORTER_PROMPT_V9
    assert "23. PROMOTION TITLE WINS" in v9
    assert "COLOGUARD PROMOTION AGREEMENT" in v9
    assert "24. OUTSOURCING TITLE WINS" in v9
    assert "MANUFACTURING OUTSOURCING AGREEMENT" in v9
    assert "25. CUSTOMIZATION SCHEDULES ARE MAINTENANCE" in v9
    assert "Customization Schedule" in v9
    assert "VALID CONTRACT SUBTYPE KEYS" in v9
    # v8 predates the three rules.
    assert "23. PROMOTION TITLE WINS" not in SORTER_PROMPT_V8
    assert "OUTSOURCING TITLE WINS" not in SORTER_PROMPT_V8
    assert "CUSTOMIZATION SCHEDULES ARE MAINTENANCE" not in SORTER_PROMPT_V8


def test_sorter_v10_marketing_title_wins():
    from src.prompts import SORTER_PROMPT_V9, SORTER_PROMPT_V10

    # v10 is a strict derivation of v9: the base is untouched, the derived
    # prompt adds the marketing-title guard for the worst persistent cell
    # (marketing 0.5/10 at 243 and 7/17 at 509 on v9 — unchanged since v6).
    assert SORTER_PROMPT_V10 != SORTER_PROMPT_V9
    assert SORTER_PROMPT_V10.startswith(SORTER_PROMPT_V9[:300])
    assert "sorter_v10" in PROMPT_VERSIONS

    v10 = SORTER_PROMPT_V10
    assert "26. MARKETING TITLE WINS" in v10
    assert "EXCLUSIVE AGENCY AND MARKETING AGREEMENT" in v10
    assert "MARKETING AND RESELLER AGREEMENT" in v10
    assert "Broker Dealer Marketing and Servicing Agreement" in v10
    assert "JOINT SUPPLY AND MARKETING AGREEMENT" in v10
    assert "not joint_venture" in v10
    assert "MARKETING AND TRANSPORTATION SERVICES AGREEMENT" in v10
    assert "Content License Agreement" in v10  # license-primary carve-out (annex inheritance)
    assert "VALID CONTRACT SUBTYPE KEYS" in v10
    # v9 predates the rule.
    assert "26. MARKETING TITLE WINS" not in SORTER_PROMPT_V9
    assert "Broker Dealer Marketing and Servicing Agreement" not in SORTER_PROMPT_V9


def test_sorter_v11_affiliate_carve_out():
    from src.prompts import SORTER_PROMPT_V10, SORTER_PROMPT_V11

    # v11 is a strict derivation of v10: the base is untouched, the derived
    # prompt adds the affiliate boundary for the rule-26 over-fire measured
    # in the v10 A/B (Cybergy + SteelVault, both "Marketing Affiliate
    # Agreement" in content, regressed by rule 26).
    assert SORTER_PROMPT_V11 != SORTER_PROMPT_V10
    assert SORTER_PROMPT_V11.startswith(SORTER_PROMPT_V10[:300])
    assert "sorter_v11" in PROMPT_VERSIONS

    v11 = SORTER_PROMPT_V11
    assert "27. AFFILIATE IS NOT MARKETING" in v11
    assert "Marketing Affiliate Agreement" in v11
    assert "affiliate, not marketing" in v11
    assert "26. MARKETING TITLE WINS" in v11
    assert "VALID CONTRACT SUBTYPE KEYS" in v11
    # v10 predates the rule.
    assert "27. AFFILIATE IS NOT MARKETING" not in SORTER_PROMPT_V10


def test_sorter_v12_strategic_alliance_title_wins():
    from src.prompts import SORTER_PROMPT_V11, SORTER_PROMPT_V12

    # v12 is a strict derivation of v11: the base is untouched, the derived
    # prompt adds the strategic_alliance title-wins guard for the 5-fail cell
    # at 509 (Iovance/Adaptimmune -> collaboration by rule-21 inversion,
    # Intricon -> license, Giggles -> consulting, FTE -> service), all five
    # explicitly titled "STRATEGIC ALLIANCE AGREEMENT" with a verified 0-risk
    # counterfactual (all 32 alliance-titled docs GT alliance).
    assert SORTER_PROMPT_V12 != SORTER_PROMPT_V11
    assert SORTER_PROMPT_V12.startswith(SORTER_PROMPT_V11[:300])
    assert "sorter_v12" in PROMPT_VERSIONS

    v12 = SORTER_PROMPT_V12
    assert "28. STRATEGIC ALLIANCE TITLE WINS" in v12
    assert "strategic_alliance, not collaboration" in v12
    assert "strategic_alliance, not license" in v12
    assert "strategic_alliance, not consulting" in v12
    assert "strategic_alliance, not service" in v12
    assert "27. AFFILIATE IS NOT MARKETING" in v12
    assert "26. MARKETING TITLE WINS" in v12
    assert "VALID CONTRACT SUBTYPE KEYS" in v12
    # v11 predates the rule.
    assert "28. STRATEGIC ALLIANCE TITLE WINS" not in SORTER_PROMPT_V11



def test_sorter_v13_maintenance_title_wins():
    from src.prompts import SORTER_PROMPT_V12, SORTER_PROMPT_V13

    # v13 is a strict derivation of v12: the base is untouched, the derived
    # prompt adds the maintenance title-wins guard for the 4-fail maintenance
    # cell at 509 (SUNTRONCORP/WELLSFARGO/PRIMEENERGY -> other by rule-13
    # inversion, AtnInternational -> service), all maintenance-titled with a
    # verified 0-risk counterfactual (34/34 maintenance-titled docs GT
    # maintenance at 509).
    assert SORTER_PROMPT_V13 != SORTER_PROMPT_V12
    assert SORTER_PROMPT_V13.startswith(SORTER_PROMPT_V12[:300])
    assert "sorter_v13" in PROMPT_VERSIONS

    v13 = SORTER_PROMPT_V13
    assert "29. MAINTENANCE TITLE WINS" in v13
    assert "maintenance, not other" in v13
    assert "maintenance, not service" in v13
    assert "Yield Maintenance Agreement" in v13
    assert "COMPLETION AND LIQUIDITY MAINTENANCE AGREEMENT" in v13
    assert "28. STRATEGIC ALLIANCE TITLE WINS" in v13
    assert "27. AFFILIATE IS NOT MARKETING" in v13
    assert "VALID CONTRACT SUBTYPE KEYS" in v13
    # v12 predates the rule.
    assert "29. MAINTENANCE TITLE WINS" not in SORTER_PROMPT_V12


def test_sorter_v14_marketing_title_wins_strengthened():
    from src.prompts import SORTER_PROMPT_V13, SORTER_PROMPT_V14

    # v14 is a strict derivation of v13: the base is untouched, the derived
    # prompt adds the rule-26 reinforcement for the 3 deterministic marketing
    # fails at 509 (Zounds -> manufacturing, PACIRA -> distributor, Audible ->
    # co_branding — identical predictions in v9-clean/v12-orig/v12-rerun/v13),
    # all marketing-titled with marketing obligations and a verified
    # 0-score-risk counterfactual (17/20 marketing-titled docs GT marketing;
    # Playboy license-primary protected by carve-out (a); HEMISPHERX already
    # wrong either way).
    assert SORTER_PROMPT_V14 != SORTER_PROMPT_V13
    assert SORTER_PROMPT_V14.startswith(SORTER_PROMPT_V13[:300])
    assert "sorter_v14" in PROMPT_VERSIONS

    v14 = SORTER_PROMPT_V14
    assert "30. MARKETING TITLE WINS" in v14
    assert "marketing, not manufacturing" in v14
    assert "marketing, not distributor" in v14
    assert "marketing, not co_branding" in v14
    assert "MANUFACTURING, DESIGN AND MARKETING AGREEMENT" in v14
    assert "STRATEGIC LICENSING, DISTRIBUTION AND MARKETING AGREEMENT" in v14
    assert "CO-BRANDING, MARKETING AND DISTRIBUTION AGREEMENT" in v14
    assert "29. MAINTENANCE TITLE WINS" in v14
    assert "28. STRATEGIC ALLIANCE TITLE WINS" in v14
    assert "VALID CONTRACT SUBTYPE KEYS" in v14
    # v13 predates the rule.
    assert "30. MARKETING TITLE WINS" not in SORTER_PROMPT_V13


def test_sorter_v15_license_primary_title_wins():
    from src.prompts import SORTER_PROMPT_V13, SORTER_PROMPT_V15

    # v15 is a strict derivation of the v13 CHAMPION (v14's rule 30 was a logic
    # repair, NOT promoted): the base is untouched and the derived prompt adds
    # rule 31 LICENSE-PRIMARY TITLE WINS, the banked v14 lesson (widen rule 26
    # carve-out (a) to any license-PRIMARY title). Cross-model failure traces on
    # the SAME v13 prompt (full-509, seed 42) show LejuHoldings "Content License
    # Agreement" -> other fails in ALL FIVE models (champion + gpt-5-nano /
    # gpt-4.1-nano / llama-4-scout / deepseek-v4-flash) and Playboy + 5 more
    # "Content License Agreement" docs -> ip/marketing/manufacturing/joint_venture
    # in the weaker models. Carve-outs preserved: maintenance (rule 13), hosting
    # (rule 14), development (rules 19/21), marketing-core (rule 26).
    assert SORTER_PROMPT_V15 != SORTER_PROMPT_V13
    assert SORTER_PROMPT_V15.startswith(SORTER_PROMPT_V13[:300])
    assert "sorter_v15" in PROMPT_VERSIONS

    v15 = SORTER_PROMPT_V15
    assert "31. LICENSE-PRIMARY TITLE WINS" in v15
    assert "Content License Agreement" in v15
    assert 'never "other"' in v15 or 'NEVER "other"' in v15
    assert "NOT ip" in v15
    # Carve-outs preserved verbatim.
    assert "rule 13" in v15
    assert "rule 14" in v15
    assert "rule 26" in v15
    # v15 derives from the champion, not v14: rule 30 (v14's marketing
    # strengthening, a logic repair) must NOT be present.
    assert "30. MARKETING TITLE WINS" not in v15
    assert "29. MAINTENANCE TITLE WINS" in v15
    assert "VALID CONTRACT SUBTYPE KEYS" in v15
    # v13 predates the rule.
    assert "31. LICENSE-PRIMARY TITLE WINS" not in SORTER_PROMPT_V13


def test_sorter_docclass_v0_registered_and_extends_v14():
    """sorter_docclass_v0 (KANBAN-033) = v14 + the hierarchical doc-class
    rules (merger_agreement class, SEC-exhibit corporate records, doc_subclass
    dimension). v14 itself stays byte-identical (a change needs a new key)."""
    from src.prompts import SORTER_PROMPT_V14, SORTER_DOCCLASS_PROMPT_V0

    assert "sorter_docclass_v0" in PROMPT_VERSIONS
    assert SORTER_DOCCLASS_PROMPT_V0.startswith(SORTER_PROMPT_V14[:300])
    p = get_prompt("sorter_docclass_v0")
    assert "31. MERGER AGREEMENT CLASS" in p
    assert "32. CORPORATE RECORDS FILED AS SEC EXHIBITS STAY CORPORATE_RECORD" in p
    assert "33. DOC SUBCLASS" in p
    assert "doc_subclass: EXACTLY ONE" in p
    # base unchanged
    assert "31. MERGER AGREEMENT CLASS" not in SORTER_PROMPT_V14
    assert "doc_subclass" not in SORTER_PROMPT_V14


def test_sorter_docclass_v1_registered_and_pins_rule_34():
    """sorter_docclass_v1 (KANBAN-033 iteration arm) = v0 + ONE rule: the
    embedded-records scope guard from the docclass pilot
    (qwen3.7-flash_sorter_docclass_v0_docclass_pilot — contract_62
    Roche/Geronimo/GenMark APM misrouted to corporate_record/bylaws by rule-32
    over-fire on its embedded bylaws Exhibit C). v0 stays byte-identical."""
    from src.prompts import SORTER_DOCCLASS_PROMPT_V0, SORTER_DOCCLASS_PROMPT_V1

    assert "sorter_docclass_v1" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_v1")
    assert "34. EMBEDDED RECORDS DO NOT CHANGE THE PARENT CLASS" in p
    assert "rule 32 applies ONLY when the document AS A WHOLE is a corporate record" in p
    # Single-change discipline: v1 carries rule 34 but NOT rule 35; v0 has neither.
    assert "35. REGISTRATION RIGHTS" not in p
    assert "34. EMBEDDED RECORDS" not in SORTER_DOCCLASS_PROMPT_V0
    assert SORTER_DOCCLASS_PROMPT_V1.startswith(SORTER_DOCCLASS_PROMPT_V0[:300])


def test_sorter_docclass_v2_registered_and_pins_rule_35():
    """sorter_docclass_v2 (KANBAN-033 iteration arm) = v0 + ONE rule: the
    registration-rights-agreement SEC-exhibit convention from the docclass
    pilot (a44registrationrightsagree — NMI/FBR EX-4.4 RRA misrouted to
    contract/other; S-1 catalog files EX-4.x instruments as record types)."""
    from src.prompts import SORTER_DOCCLASS_PROMPT_V0, SORTER_DOCCLASS_PROMPT_V2

    assert "sorter_docclass_v2" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_v2")
    assert "35. REGISTRATION RIGHTS AGREEMENTS FILED AS SEC EXHIBITS" in p
    assert "rights_instrument" in p
    assert "34. EMBEDDED RECORDS" not in p
    assert "35. REGISTRATION RIGHTS" not in SORTER_DOCCLASS_PROMPT_V0
    assert SORTER_DOCCLASS_PROMPT_V2.startswith(SORTER_DOCCLASS_PROMPT_V0[:300])


def test_sorter_docclass_v3_registered_and_pins_rules_34_35():
    """sorter_docclass_v3 (KANBAN-033) = the Phase 3.5 MERGE of the two
    validated single-change lessons applied to the SAME v0 base: rule 34
    (embedded-records scope guard, from v1) AND rule 35 (RRA exhibit
    convention, from v2). Motivated by the same-surface A/B
    (qwen3.7-flash_sorter_docclass_{v0,v1,v2}_docclass_ab30, fp d3d7b335…,
    stratified-30 seed 42): v2 recovered the 5-row EX-4.x doc_type cluster
    (exact 0.6667 -> 0.8000) while v1's rule-34 target was absent from the
    sample — the merge carries both disjoint lessons."""
    from src.prompts import (
        SORTER_DOCCLASS_PROMPT_V0,
        SORTER_DOCCLASS_PROMPT_V3,
    )

    assert "sorter_docclass_v3" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_v3")
    # Both rules present, in rule-number order.
    assert "34. EMBEDDED RECORDS DO NOT CHANGE THE PARENT CLASS" in p
    assert "35. REGISTRATION RIGHTS AGREEMENTS FILED AS SEC EXHIBITS" in p
    assert p.index("34. EMBEDDED RECORDS") < p.index("35. REGISTRATION RIGHTS")
    # Merge discipline: v3 = v0 + rules 34 AND 35 (v0 has neither).
    assert "34. EMBEDDED RECORDS" not in SORTER_DOCCLASS_PROMPT_V0
    assert "35. REGISTRATION RIGHTS" not in SORTER_DOCCLASS_PROMPT_V0
    assert SORTER_DOCCLASS_PROMPT_V3.startswith(SORTER_DOCCLASS_PROMPT_V0[:300])


def test_sorter_docclass_vision_v0_registered_and_pins_vision_contract():
    """sorter_docclass_vision_v0 (KANBAN-033 vision arm) = the vision-mode
    twin of the completed docclass text prompt: 7 classes, rules 31-35,
    the doc_subclass tag, the UNREADABLE sentinel (vision-primary with text
    fallback), and the ``## Output format`` split marker."""
    from src.prompts import SORTER_DOCCLASS_VISION_PROMPT_V0

    assert "sorter_docclass_vision_v0" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_vision_v0")
    # All 7 docclass labels in the label list.
    for key in ("contract", "corporate_record", "due_diligence", "correspondence",
                "compliance_filing", "court_opinion", "merger_agreement"):
        assert key in p, f"vision prompt missing class {key!r}"
    # The docclass rules are carried over (vision-adapted).
    assert "31. MERGER AGREEMENT CLASS" in p
    assert "32. CORPORATE RECORDS FILED AS SEC EXHIBITS" in p
    assert "33. DOC SUBCLASS" in p
    assert "34. EMBEDDED RECORDS DO NOT CHANGE THE PARENT CLASS" in p
    assert "35. REGISTRATION RIGHTS AGREEMENTS FILED AS SEC EXHIBITS" in p
    # Vision-primary contract: subclass tag + UNREADABLE sentinel + split marker.
    assert "<subclass>all_cash</subclass>" in p
    assert "<label>UNREADABLE</label>" in p
    assert "The system will re-try this document via its text." in p
    assert "## Output format" in p
    # The text docclass prompt is untouched by the vision twin.
    assert "<label>" not in get_prompt("sorter_docclass_v3")


def test_sorter_docclass_v6_registered_and_pins_rule_36_sharpened():
    """sorter_docclass_v6 (KANBAN-033 iteration arm) = v3 + ONE rule: rule 36
    SHARPENED from the v4 diag30 A/B — the rule-31 title list is declared
    illustrative and multi-agreement files are governed by the primary
    agreement (contract_33's model reasoning showed it second-guessing rule
    31's enumeration on a TRANSACTION AGREEMENT + RRA-exhibit-E file)."""
    from src.prompts import SORTER_DOCCLASS_PROMPT_V3, SORTER_DOCCLASS_PROMPT_V6

    assert "sorter_docclass_v6" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_v6")
    assert "36. M&A PACKAGE MACHINERY GOVERNS ANCILLARY INSTRUMENTS" in p
    assert "rule 31's M&A-family title list is ILLUSTRATIVE" in p
    assert '"TRANSACTION AGREEMENT"' in p
    assert "WHEN A FILE CONTAINS MORE THAN ONE AGREEMENT" in p
    assert "Rule 35 applies ONLY when the document's own title is" in p
    # Single-change discipline: v6 carries rule 36 (sharpened) but NOT rule 37.
    assert "37. AGREEMENT PACKAGES" not in p
    assert "36. M&A PACKAGE MACHINERY" not in SORTER_DOCCLASS_PROMPT_V3
    assert SORTER_DOCCLASS_PROMPT_V6.startswith(SORTER_DOCCLASS_PROMPT_V3[:300])
    # v4's rule-36 text is untouched (never mutate a version that has run).
    from src.prompts import SORTER_DOCCLASS_PROMPT_V4
    assert "ILLUSTRATIVE, not exhaustive" not in SORTER_DOCCLASS_PROMPT_V4


def test_sorter_docclass_v7_registered_and_pins_extended_universe_rules():
    """sorter_docclass_v7 (KANBAN-101) = v6 + rules 37–43 + widened doc_subclass
    output contract for correspondence/insurance_claim dimensions."""
    from src.prompts import SORTER_DOCCLASS_PROMPT_V6, SORTER_DOCCLASS_PROMPT_V7

    assert "sorter_docclass_v7" in PROMPT_VERSIONS
    p = get_prompt("sorter_docclass_v7")
    assert "37. AGREEMENT PACKAGES" in p
    assert "38. INSURANCE CLAIM CLASS" in p
    assert "39. CORRESPONDENCE SUBCLASS" in p
    assert "43. CONTRACT VS INSURANCE CLAIM DISAMBIGUATION" in p
    assert "correspondence, or insurance_claim (rules 33/39/40)" in p
    assert SORTER_DOCCLASS_PROMPT_V7.startswith(SORTER_DOCCLASS_PROMPT_V6[:300])
    assert "37. AGREEMENT PACKAGES" not in SORTER_DOCCLASS_PROMPT_V6


def test_sorter_docclass_correspondence_v3_speech_act_overrides_hub_lexicon():
    """KANBAN-103 GEPA v3: .replace() of frozen v2; rule 47 demand speech-act."""
    from src.prompts import (
        CORRESPONDENCE_SUBCLASS_V3,
        SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V2,
        SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V3,
    )

    assert "sorter_docclass_correspondence_v3" in PROMPT_VERSIONS
    v2 = get_prompt("sorter_docclass_correspondence_v2")
    v3 = get_prompt("sorter_docclass_correspondence_v3")
    assert v3 is SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V3
    assert v2 is SORTER_DOCCLASS_CORRESPONDENCE_PROMPT_V2
    assert v3.startswith(v2[:400])
    assert "46. HUB DEMAND MARKERS" in v3
    assert "47. DEMAND IS THE SPEECH ACT" in v3
    assert "47. DEMAND IS THE SPEECH ACT" not in v2
    assert "OVERRIDES rule 46" in CORRESPONDENCE_SUBCLASS_V3
    assert "performs the demand" in v3
    assert "we could send a demand letter" in v3
    assert "please draft a demand letter" in v3
    assert "NOT demand" in v3
    assert "46. HUB DEMAND MARKERS" in v2
    assert "speech act" not in v2.lower() or "47." not in v2


def test_sorter_docclass_prompt_option_list_matches_schema():
    """The doc_subclass options visible in the docclass prompts must match the
    DOCCLASS_SCHEMA enum exactly — a subclass the model can output must be in
    the prompt, and nothing in the prompt may be rejected by the schema.
    Parametrized over every docclass version (v0 baseline, v1/v2 candidates,
    v3 merge)."""
    import re

    import pytest

    from agents.sorter_agent import (
        DOCCLASS_CLASSES,
        DOCCLASS_SCHEMA,
        DOC_SUBCLASS_KEYS,
        SorterAgent,
    )

    enum = set(DOCCLASS_SCHEMA["properties"]["doc_subclass"]["enum"])
    assert enum == set(DOC_SUBCLASS_KEYS)

    for version in ("sorter_docclass_v0", "sorter_docclass_v1",
                    "sorter_docclass_v2", "sorter_docclass_v3",
                    "sorter_docclass_v4", "sorter_docclass_v5",
                    "sorter_docclass_v6", "sorter_docclass_v7",
                    "sorter_docclass_correspondence_v0",
                    "sorter_docclass_correspondence_v1",
                    "sorter_docclass_correspondence_v2",
                    "sorter_docclass_correspondence_v3",
                    "sorter_mailroom_v0"):
        prompt = SorterAgent(prompt_version=version,
                             doc_classes=DOCCLASS_CLASSES,
                             schema=DOCCLASS_SCHEMA).system_prompt()
        # Schema-key presence is lineage-scoped: pilot variants teach ALL
        # four dimensions; legacy v0..v6 were frozen before the
        # correspondence/insurance dimensions existed and are never mutated
        # after a run — they must carry the merger/corporate keys only.
        # HUB-041: the mailroom-named v8 lineages also teach the v8 LOB
        # tokens (property/auto); every docclass version frozen BEFORE the
        # v8 corpus (pilot v0-v3, v7, correspondence) predates them and is
        # never mutated — property/auto are excluded from their expectations.
        if version == "sorter_mailroom_v0":
            expected_keys = DOC_SUBCLASS_KEYS
        elif ("pilot" in version or version == "sorter_docclass_v7"
                or "correspondence" in version):
            expected_keys = [k for k in DOC_SUBCLASS_KEYS
                             if k not in {"property", "auto"}]
        else:
            legacy_excluded = {"demand", "attorney_demand", "meeting_request",
                               "press_release", "memo", "email", "letter",
                               "notice", "carrier", "pde", "outpatient",
                               "inpatient", "property", "auto"}
            expected_keys = [k for k in DOC_SUBCLASS_KEYS if k not in legacy_excluded]
        for key in expected_keys:
            assert key in prompt, f"{version}: doc_subclass key {key!r} missing from the prompt"
        # The output contract names the field.
        assert "- doc_subclass: EXACTLY ONE" in prompt
        assert "merger_agreement" in prompt


def test_contracts_v2_is_completeness_first():
    prompt = get_prompt("contracts_specialist_v2")
    assert "COMPLETENESS IS THE PRIORITY" in prompt
    assert "one item per distinct obligation" in prompt.lower()
    assert "operative language" in prompt.lower()
    assert "confidence" in prompt


def test_legalbench_task_v1_hearsay_doctrine():
    """legalbench_task_v1 is a strict derivation of v0 that adds ONE hearsay-
    doctrine rule to the system prompt (KANBAN-026 GEPA iteration).

    Data: qwen3.7-flash_legalbench_task_v0_test @94 (4 runs, temp 0.0) =
    0.7766/0.7872/0.7766/0.7872 (band ±1 row); 18 deterministic failures:
    cluster A purpose-test misses (9: 47/76/77/78/79/80/82/85/86, statements
    offered for effect-on-listener / declarant state-of-mind wrongly called
    hearsay), cluster B statement-scope escapes (8: 39/50/58/61/68/69/71/94,
    party-admission / non-verbal assertion / writings / verbal-act wrongly
    called not-hearsay), cluster C in-court carve-out (1: 23). v1 = v0 + the
    truth-of-matter purpose test + statement scope (writings, assertive non-
    verbal conduct) + in-court carve-out, regression-scanned against all 71
    correct rows (no predicted flip).
    """
    from src.prompts import LEGALBENCH_TASK_PROMPT_V0, LEGALBENCH_TASK_PROMPT_V1

    # v1 is a strict derivation of v0: base untouched, ONE doctrine rule added.
    assert LEGALBENCH_TASK_PROMPT_V1 != LEGALBENCH_TASK_PROMPT_V0
    assert LEGALBENCH_TASK_PROMPT_V1.startswith(LEGALBENCH_TASK_PROMPT_V0[:300])
    assert "legalbench_task_v1" in PROMPT_VERSIONS

    v1 = LEGALBENCH_TASK_PROMPT_V1
    # v0's output-format rules survive intact.
    assert "Output ONLY the answer" in v1
    assert "{{valid_classes}}" in v1
    assert "Output the answer on a single line and nothing else." in v1
    # The doctrine rule: purpose test (truth of the matter asserted).
    assert "offered to prove the truth of the matter asserted" in v1
    assert "the listener was told, knew, or was provoked" in v1
    # Statement scope: writings + assertive non-verbal conduct.
    assert "emails, texts, reports, cards, signs" in v1
    assert "non-verbal conduct" in v1
    # Party's own statement is still hearsay (admission = admissibility only).
    assert "party admission" in v1.lower()
    assert "exception to admissibility" in v1
    # In-court carve-out.
    assert "in court, under oath" in v1
    # v0 predates the doctrine.
    assert "offered to prove the truth of the matter asserted" not in LEGALBENCH_TASK_PROMPT_V0
    assert "effect on the listener" not in LEGALBENCH_TASK_PROMPT_V0


def test_legalbench_task_v2_operative_fact_purpose_carveout():
    """legalbench_task_v2 is a strict derivation of v1 that refines rule 6
    with the purpose-first ACT/STATE carve-out + knowledge-contradiction
    repair (KANBAN-026 arm 5).

    Data: qwen3.7-flash_legalbench_task_v1_test @94 = 0.8511 (80/94).
    Full-reasoning diagnostic on all 14 v1 failures (raw OpenRouter
    reasoning_content, same v1 prompt, temp 0.0): 8 runner artifacts (the
    _answer_task 512-token reasoning truncation + reasoning_effort=none
    retry degrades rows 21/30/44/79/82/85/86 that full reasoning answers
    correctly — runner fix banked, NOT a prompt rule) + 6 genuine content
    failures. The 6: (91) rule_contradiction — model quotes v1's YES-example
    "'I am aware of the conduct' to prove knowledge" verbatim on a
    knowledge-acquaintance row GT labels No; (74) pointing offered to prove
    the identification ACT; (78) defamatory statement = the verbal act
    damaging reputation; (72) protest signs offered to show the workers'
    grievance, not the truth of the demand; (68) stickers asserting support
    ARE assertive (model misread the "poster hung as decoration" example);
    (39) will-change 1-off, banked. v2 = v1.replace(rule 6) with ONE lesson
    (read the ISSUE phrase first: content-truth → Yes, ACT/STATE → No) +
    contradiction repair (knowledge-acquaintance → No; intent-plan → Yes
    guardrail), regression-scanned against all 80 v1-correct rows.
    """
    from src.prompts import LEGALBENCH_TASK_PROMPT_V1, LEGALBENCH_TASK_PROMPT_V2

    # v2 is a strict derivation of v1: base + v0/v1 rules survive, rule 6 is
    # the only thing replaced.
    assert LEGALBENCH_TASK_PROMPT_V2 != LEGALBENCH_TASK_PROMPT_V1
    assert LEGALBENCH_TASK_PROMPT_V2.startswith(LEGALBENCH_TASK_PROMPT_V1[:300])
    assert "legalbench_task_v2" in PROMPT_VERSIONS

    v2 = LEGALBENCH_TASK_PROMPT_V2
    # v0's output-format rules + the v1 doctrine skeleton survive.
    assert "Output ONLY the answer" in v2
    assert "Output the answer on a single line and nothing else." in v2
    assert "offered to prove the truth of the matter asserted" in v2
    assert "in court, under oath" in v2
    assert "party admission" in v2.lower()
    # Purpose-first: the issue phrase names the fact to be proved.
    assert "names the fact to be proved" in v2
    # The decision question: is X the content (Yes) or an ACT/STATE shown by
    # the making (No)?
    assert "X IS the statement's content" in v2
    assert "an ACT or a STATE shown by the making" in v2
    # ACT carve-out: identification act + defamatory utterance as the act —
    # conditional on the issue being the act, NOT the content (rows 74/78 No,
    # while 64/42/52 whose issue IS the content stay Yes).
    assert "pointing offered to show that X identified the suspect" in v2
    assert "the utterance itself is the harm" in v2
    assert "not whether the identification was correct" in v2
    # STATE carve-out: listener told/knew + declarant feeling + grievance.
    assert "the listener was told, knew, or was provoked" in v2
    assert "workers' grievance behind protest signs" in v2
    # Knowledge-acquaintance → NO (the contradiction repair): a statement
    # naming a person or thing shows the speaker's acquaintance with it.
    assert "shows the speaker's acquaintance with it" in v2
    # The harmful v1 YES-example ("I am aware of the conduct" → knowledge)
    # is REMOVED — it contradicted GT on rows 82/91.
    assert '"I am aware of the conduct" to prove knowledge' not in v2
    # Content-is-X still covers the knowledge rows whose content IS the
    # knowledge (rows 59/60/61/71/84 stay Yes).
    assert "an email acknowledging" in v2
    assert "the content itself IS the knowledge" in v2
    # Intent-plan guardrail: statements of intent offered to prove the
    # planned act stay YES (row 44 email-plan → ownership).
    assert "statement of intent or plan offered to prove the planned act" in v2
    # Sticker boundary drawn BOTH ways: stickers asserting support → YES
    # (row 68), protest signs showing grievance → NO (row 72).
    assert "stickers asserting support of a cause" in v2
    assert "not that the demand is true" in v2
    # Reputation-harm boundary: gossip whose content IS the harm → YES
    # (row 42); defamatory utterance as the operative act → NO (row 78).
    assert "gossip asserting bad things about Alice" in v2


def test_legalbench_task_v4_hygiene_fix():
    """legalbench_task_v4 is the subtask-series base: v3 with TWO hygiene
    repairs and no doctrine change — (1) the stray `"` character prepended to
    the prohibition rule by the v3 string-concatenation construction, and (2)
    the rule-numbering collision (v3 numbers the prohibition rule "6." while
    the hearsay doctrine rule is also "6.").

    Data: the 7 CUAD subtask prompts (legalbench_task_v3_<subtask>) were
    aliases of generic v3 carrying the hearsay doctrine that never fires on
    CUAD clause tasks; the subtask runs at temp 0.1 show the model decides
    from the task few-shot alone (see v4_<subtask> tests for the failure
    clusters). v4 becomes the hygiene-fixed base for the subtask-specific
    v4_<subtask> versions.
    """
    from src.prompts import LEGALBENCH_TASK_PROMPT_V3, LEGALBENCH_TASK_PROMPT_V4

    assert LEGALBENCH_TASK_PROMPT_V4 != LEGALBENCH_TASK_PROMPT_V3
    assert LEGALBENCH_TASK_PROMPT_V4.startswith(LEGALBENCH_TASK_PROMPT_V3[:300])
    assert "legalbench_task_v4" in PROMPT_VERSIONS

    v3, v4 = LEGALBENCH_TASK_PROMPT_V3, LEGALBENCH_TASK_PROMPT_V4
    # The stray quote bug: v3 = V2 + """" prepends a literal `"` before the
    # prohibition rule. v4 removes it.
    assert 'nothing else."\n\n6. SPECIAL CASE' in v3
    assert 'nothing else."\n\n6. SPECIAL CASE' not in v4
    # Numbering collision fixed: v3 has TWO "6." rules (hearsay + prohibition),
    # v4 renumbers the prohibition rule to 7.
    assert v3.count("\n6. ") == 2
    assert v4.count("\n6. ") == 1
    assert "\n7. SPECIAL CASE — Prohibition clauses:" in v4
    # No doctrine change: everything else survives byte-identical.
    assert "offered to prove the truth of the matter asserted" in v4
    assert "Output ONLY the answer" in v4


def test_legalbench_task_v4_competitive_restriction_exception_rule():
    """legalbench_task_v4_competitive_restriction_exception = v4 + ONE rule:
    the conditional-permission carveout shape. Data: cuad_competitive_
    restriction_exception_0 failed DETERMINISTICALLY on the 6-row CRE surface
    (fp de6ae646, temp 0.1) — 0.8333 in BOTH the anti_assignment-named sweep
    and the competitive_restriction_exception-named run. GT Yes: the
    IGER/CERES clause is a conditional-permission carveout ("if IGER would
    enter into any agreement ... with a not-for-profit third party ... such
    agreement must provide that (i) IGER will receive the exclusive right
    (subject to Articles 5.1.2(a) and 5.2) ...") — an exception framework
    with no explicit "except"/"provided, however" qualifier, which the task
    few-shot never demonstrates. The rule is stated as a FAMILY rule
    (permission structure = carveout), not a document recall.
    """
    from src.prompts import LEGALBENCH_TASK_PROMPT_V4, LEGALBENCH_TASK_PROMPT_V4_CRE

    assert LEGALBENCH_TASK_PROMPT_V4_CRE != LEGALBENCH_TASK_PROMPT_V4
    assert LEGALBENCH_TASK_PROMPT_V4_CRE.startswith(LEGALBENCH_TASK_PROMPT_V4)
    assert "legalbench_task_v4_competitive_restriction_exception" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["legalbench_task_v4_competitive_restriction_exception"] is LEGALBENCH_TASK_PROMPT_V4_CRE

    cre = LEGALBENCH_TASK_PROMPT_V4_CRE
    assert "COMPETITIVE-RESTRICTION EXCEPTIONS (this task)" in cre
    assert "conditional-PERMISSION" in cre
    assert "The permission structure IS the carveout" in cre
    assert "may enter into a specified agreement" in cre.lower()
    assert "subject to stated conditions" in cre
    # Negative boundary: a restriction/termination right without a permission
    # stays No (rows 3-5 of the CRE surface).
    assert "only states a restriction or a termination right" in cre


def test_legalbench_task_v4_covenant_not_to_sue_rule():
    """legalbench_task_v4_covenant_not_to_sue = v4 + ONE rule: conduct-
    restriction covenants count as covenants not to sue even without the
    word "sue". Data: cuad_covenant_not_to_sue_2 oscillated on the 6-row
    CNTS surface (fp 0068f5b9, temp 0.1) — 1.0 / 0.8333 across two runs. GT
    Yes: "Allied shall not at any time do, or cause to be done, directly or
    indirectly any act that may impair or tarnish any part of Newegg's
    goodwill and reputation in the Newegg Marks and the Newegg Products" — a
    covenant restricting CONDUCT toward the counterparty's IP. The model
    over-matched on literal "contest validity / bring a claim" vocabulary.
    Weaker evidence (1/2) than the CRE cluster -> logic-repair grade, stated
    as a family rule generalizing to any conduct-restriction covenant.
    """
    from src.prompts import LEGALBENCH_TASK_PROMPT_V4, LEGALBENCH_TASK_PROMPT_V4_CNTS

    assert LEGALBENCH_TASK_PROMPT_V4_CNTS != LEGALBENCH_TASK_PROMPT_V4
    assert LEGALBENCH_TASK_PROMPT_V4_CNTS.startswith(LEGALBENCH_TASK_PROMPT_V4)
    assert "legalbench_task_v4_covenant_not_to_sue" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["legalbench_task_v4_covenant_not_to_sue"] is LEGALBENCH_TASK_PROMPT_V4_CNTS

    cnts = LEGALBENCH_TASK_PROMPT_V4_CNTS
    assert "COVENANT NOT TO SUE (this task)" in cnts
    assert "need NOT use the words" in cnts
    assert "impair, tarnish, or challenge" in cnts
    assert "conduct that would undermine the counterparty's IP rights" in cnts
    # Negative boundary: unrelated duties (record-keeping, audit, payment)
    # stay No (rows 3-5 of the CNTS surface).
    assert "record-keeping, audit, payment" in cnts


def test_legalbench_subtask_v4_keys_resolve():
    """All seven v4_<subtask> keys resolve; the two rule versions are the
    CRE/CNTS specialists, the other five are the hygiene-fixed v4 base (they
    sat at 1.0/6 on their surfaces — no measurable headroom, so no rule)."""
    from src.prompts import (
        LEGALBENCH_TASK_PROMPT_V4,
        LEGALBENCH_TASK_PROMPT_V4_CRE,
        LEGALBENCH_TASK_PROMPT_V4_CNTS,
    )

    base_keys = [
        "legalbench_task_v4_anti_assignment",
        "legalbench_task_v4_audit_rights",
        "legalbench_task_v4_cap_on_liability",
        "legalbench_task_v4_change_of_control",
        "legalbench_task_v4_effective_date",
    ]
    for k in base_keys:
        assert PROMPT_VERSIONS[k] is LEGALBENCH_TASK_PROMPT_V4, k
    assert PROMPT_VERSIONS["legalbench_task_v4_competitive_restriction_exception"] is LEGALBENCH_TASK_PROMPT_V4_CRE
    assert PROMPT_VERSIONS["legalbench_task_v4_covenant_not_to_sue"] is LEGALBENCH_TASK_PROMPT_V4_CNTS
    # v3_<subtask> identity preserved (their runs used those strings).
    from src.prompts import LEGALBENCH_TASK_PROMPT_V3

    for k in ("legalbench_task_v3_anti_assignment", "legalbench_task_v3_effective_date"):
        assert PROMPT_VERSIONS[k] is LEGALBENCH_TASK_PROMPT_V3, k


def test_sorter_prompt_mentions_classes():
    prompt = get_prompt("sorter")
    for cls in ("contract", "corporate_record", "due_diligence", "court_opinion"):
        assert cls in prompt


def test_get_prompt_unknown_raises():
    with pytest.raises(KeyError):
        get_prompt("does_not_exist")


def test_list_prompts_sorted():
    versions = list_prompts()
    assert versions == sorted(versions)
    assert "sorter" in versions


def test_prompt_templates_matches_registry():
    assert PROMPT_TEMPLATES() == PROMPT_VERSIONS


def test_default_prompt_version_is_sorter():
    assert DEFAULT_PROMPT_VERSION == "sorter"


def test_judge_prompts_are_distinct():
    judge = get_prompt("judge")
    cls = get_prompt("judge-classification")
    corr = get_prompt("judge-correctness")
    assert judge != cls != corr


def test_contracts_v12_field_accuracy_and_rescan_rules():
    from src.prompts import CONTRACTS_SPECIALIST_PROMPT_V11, CONTRACTS_SPECIALIST_PROMPT_V12

    # v12 is a strict derivation of v11: the base is untouched, the derived
    # prompt adds the field-accuracy and re-scan duties.
    assert CONTRACTS_SPECIALIST_PROMPT_V12 != CONTRACTS_SPECIALIST_PROMPT_V11
    assert CONTRACTS_SPECIALIST_PROMPT_V12.startswith(CONTRACTS_SPECIALIST_PROMPT_V11[:300])
    assert "contracts_specialist_v12" in PROMPT_VERSIONS

    v12 = CONTRACTS_SPECIALIST_PROMPT_V12
    # Effective-date rule: defined-term preference, full date phrase.
    assert 'DEFINES an "Effective Date"' in v12
    assert "the defined term wins" in v12
    # Governing-law verbatim-in-full duty (containment fix).
    assert "VERBATIM and IN FULL" in v12
    assert "conflict-of-laws qualifier" in v12
    # Re-scan duty names the families the 5-doc sample missed.
    assert "RE-SCAN DUTY" in v12
    for family in ("volume restrictions", "caps on liability", "uncapped liability",
                   "audit rights", "third-party beneficiary", "change of control",
                   "anti-assignment"):
        assert family in v12, f"v12 missing re-scan family {family}"
    # Truncation honesty: never fabricate for the omitted middle.
    assert "never fabricate a clause for it" in v12
    # v11 predates the new rules.
    v11 = CONTRACTS_SPECIALIST_PROMPT_V11
    assert "RE-SCAN DUTY" not in v11
    assert "VERBATIM and IN FULL" not in v11


def test_contracts_v18_family_fidelity_catalog():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V17,
        CONTRACTS_SPECIALIST_PROMPT_V18,
    )

    # v18 is a strict derivation of v17: the base is untouched, the derived
    # prompt replaces the terse family list with the shape-level catalog and
    # narrows the exclusion rule. The v17 grain (length-anchored, 10-25
    # words) is kept unchanged.
    assert CONTRACTS_SPECIALIST_PROMPT_V18 != CONTRACTS_SPECIALIST_PROMPT_V17
    assert CONTRACTS_SPECIALIST_PROMPT_V18.startswith(CONTRACTS_SPECIALIST_PROMPT_V17[:300])
    assert "contracts_specialist_v18" in PROMPT_VERSIONS

    v18 = CONTRACTS_SPECIALIST_PROMPT_V18
    # The 26-item CUAD-mirroring catalog with operative shapes is present.
    assert "mirroring the CUAD clause categories 1:1" in v18
    for family in ("Anti-Assignment", "Change Of Control", "Exclusivity", "Non-Compete",
                   "No-Solicit Of Customers", "No-Solicit Of Employees",
                   "Non-Disparagement", "Most-Favored-Nation", "ROFR/ROFO/ROFN",
                   "Revenue/Profit Sharing", "Price Restrictions", "Minimum Commitment",
                   "Volume Restriction", "IP Ownership Assignment",
                   "Joint IP Ownership", "License Grant", "Source Code Escrow",
                   "Post-Termination Services", "Audit Rights", "Uncapped Liability",
                   "Cap On Liability", "Liquidated Damages", "Insurance",
                   "Covenant Not To Sue", "Third Party Beneficiary"):
        assert f"{family}:" in v18, f"v18 missing catalog entry {family}"
    # Data-backed shapes for the families the 50-doc decomposition missed.
    assert "in no event shall either party be liable" in v18
    assert "elects not to prosecute or maintain" in v18
    assert "Change in Control" in v18
    # Family-term definitions are items even though general definitions are not.
    assert "definitions ARE the category's" in v18
    assert "operative text, even though general definitions are not items" in v18
    # Exclusion rule narrowed: family clauses inside indemnity/damages sections count.
    assert "never excluded because of WHERE it sits" in v18
    assert "pure indemnification obligations" in v18
    # The v17 length-anchored grain is intact.
    assert "typically 10-25 words" in v18
    # v17 predates the catalog.
    v17 = CONTRACTS_SPECIALIST_PROMPT_V17
    assert "mirroring the CUAD clause categories 1:1" not in v17


def test_contracts_v19_worked_examples_and_span_discipline():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V18,
        CONTRACTS_SPECIALIST_PROMPT_V19,
    )

    # v19 is a strict derivation of v18: the base is untouched, the derived
    # prompt adds the worked span examples (license-grant shapes drawn from
    # the residual misses) and the one-item-per-requirement span discipline.
    assert CONTRACTS_SPECIALIST_PROMPT_V19 != CONTRACTS_SPECIALIST_PROMPT_V18
    assert CONTRACTS_SPECIALIST_PROMPT_V19.startswith(CONTRACTS_SPECIALIST_PROMPT_V18[:300])
    assert "contracts_specialist_v19" in PROMPT_VERSIONS

    v19 = CONTRACTS_SPECIALIST_PROMPT_V19
    # Worked span examples: positive license shapes + verified negatives.
    assert "WORKED SPAN EXAMPLES" in v19
    assert "grants and assigns by means of present assignment" in v19
    assert "restrictions ON the licensed rights are License Grant items" in v19
    assert "options to license or acquire rights ARE items" in v19
    assert "NEGATIVE examples" in v19
    assert "trademark-hygiene" in v19
    assert "one operative requirement, one item" in v19
    # Span discipline: dedupe duty against repeats and sentence/fragment pairs.
    assert "SPAN DISCIPLINE" in v19
    assert "never emit a clause" in v19
    assert "drop the redundant copies" in v19
    # The v18 catalog and exclusion guard are intact.
    assert "mirroring the CUAD clause categories 1:1" in v19
    assert "never excluded because of WHERE it sits" in v19
    # v18 predates the worked examples.
    v18 = CONTRACTS_SPECIALIST_PROMPT_V18
    assert "WORKED SPAN EXAMPLES" not in v18
    assert "SPAN DISCIPLINE" not in v18


def test_contracts_v20_non_obligation_field_fidelity():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V19,
        CONTRACTS_SPECIALIST_PROMPT_V20,
    )

    # v20 is a strict derivation of v19: the base is untouched, the derived
    # prompt adds the four non-obligation field rules from the v19 per-field
    # failure audit (renewal_terms, term_length, governing_law,
    # termination_clauses).
    assert CONTRACTS_SPECIALIST_PROMPT_V20 != CONTRACTS_SPECIALIST_PROMPT_V19
    assert CONTRACTS_SPECIALIST_PROMPT_V20.startswith(CONTRACTS_SPECIALIST_PROMPT_V19[:300])
    assert "contracts_specialist_v20" in PROMPT_VERSIONS

    v20 = CONTRACTS_SPECIALIST_PROMPT_V20
    # renewal_terms: evergreen clauses + deal-terms tables.
    assert "EVERGREEN CLAUSES" in v20
    assert "shall continue in full force and effect thereafter" in v20
    assert "DEAL-TERMS TABLES" in v20
    # term_length: defined-Term sentences carve out of the existing
    # no-definitions rule.
    assert "DEFINED-TERM SENTENCES" in v20
    assert "DEFINES THE TERM ITSELF" in v20
    assert "do NOT answer with the definition of a defined term" in v20
    # governing_law: regulatory-jurisdiction sentences included.
    assert "regulatory-jurisdiction" in v20
    assert "Canadian Radio-television and Telecommunications" in v20
    # termination_clauses: redacted sections still count via heading+marker.
    assert "REDACTED SECTIONS" in v20
    assert "Termination for\n     Convenience. [***]." in v20 or "Termination for Convenience. [***]." in v20
    # v19's worked examples and span discipline are intact.
    assert "WORKED SPAN EXAMPLES" in v20
    assert "SPAN DISCIPLINE" in v20
    # v19 predates the field rules.
    v19 = CONTRACTS_SPECIALIST_PROMPT_V19
    assert "EVERGREEN CLAUSES" not in v19
    assert "DEFINED-TERM SENTENCES" not in v19
    assert "REDACTED SECTIONS" not in v19


def test_contracts_v21_merge_arm():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V20,
        CONTRACTS_SPECIALIST_PROMPT_V21,
    )

    # v21 is the v20 prompt TEXT at reasoning_effort=none (the merge arm:
    # v19's ko content + v20's four field rules, with the max-reasoning
    # parse-error risk retired). The prompt is identical to v20; the
    # version key + reasoning param are the experiment identity.
    assert CONTRACTS_SPECIALIST_PROMPT_V21 == CONTRACTS_SPECIALIST_PROMPT_V20
    assert "contracts_specialist_v21" in PROMPT_VERSIONS
    v21 = CONTRACTS_SPECIALIST_PROMPT_V21
    assert "WORKED SPAN EXAMPLES" in v21
    assert "SPAN DISCIPLINE" in v21
    assert "EVERGREEN CLAUSES" in v21
    assert "DEFINED-TERM SENTENCES" in v21
    assert "REDACTED SECTIONS" in v21


def test_contracts_v22_ko_recovery_rules():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V21,
        CONTRACTS_SPECIALIST_PROMPT_V22,
    )

    # v22 is a strict derivation of v21: the base is untouched, the derived
    # prompt fixes the ko regression (ellipsis abbreviation + over-dedupe).
    assert CONTRACTS_SPECIALIST_PROMPT_V22 != CONTRACTS_SPECIALIST_PROMPT_V21
    assert CONTRACTS_SPECIALIST_PROMPT_V22.startswith(CONTRACTS_SPECIALIST_PROMPT_V21[:300])
    assert "contracts_specialist_v22" in PROMPT_VERSIONS

    v22 = CONTRACTS_SPECIALIST_PROMPT_V22
    # Verbatim completeness: no ellipsis abbreviation, no truncated quotes.
    assert "VERBATIM COMPLETENESS" in v22
    assert "NEVER abbreviate with ellipses" in v22
    assert "never truncate a quote" in v22
    # Dedupe narrowed: overlapping wording is NOT duplication.
    assert "overlapping wording is NOT duplication" in v22
    assert "drop only exact repeats and sentence/fragment" in v22
    assert "never a distinct requirement whose wording" in v22
    # All prior content intact.
    assert "WORKED SPAN EXAMPLES" in v22
    assert "EVERGREEN CLAUSES" in v22
    assert "DEFINED-TERM SENTENCES" in v22
    # v21 predates the ko-recovery rules.
    v21 = CONTRACTS_SPECIALIST_PROMPT_V21
    assert "VERBATIM COMPLETENESS" not in v21
    assert "overlapping wording is NOT duplication" not in v21


def test_contracts_v23_residual_34_examples():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V22,
        CONTRACTS_SPECIALIST_PROMPT_V23,
    )

    # v23 is a strict derivation of v22: the base is untouched, the derived
    # prompt adds the second worked-example set built from the 34 residual
    # spans (v18-matched, v22-missed) and sharpens the trademark negative.
    assert CONTRACTS_SPECIALIST_PROMPT_V23 != CONTRACTS_SPECIALIST_PROMPT_V22
    assert CONTRACTS_SPECIALIST_PROMPT_V23.startswith(CONTRACTS_SPECIALIST_PROMPT_V22[:300])
    assert "contracts_specialist_v23" in PROMPT_VERSIONS

    v23 = CONTRACTS_SPECIALIST_PROMPT_V23
    # Recurring missed shapes from the residual 34.
    assert "audited-financial-statement delivery IS an Audit Rights item" in v23
    assert "Fox will remit all VGSL Revenue to Licensee" in v23
    assert "all-requirements supply" in v23
    assert "joint trademark registration" in v23
    assert "sell-off revenues subject to royalties" in v23
    assert "at cost without markup" in v23
    # The trademark negative is sharpened, not removed.
    assert "mark-HYGIENE duties" in v23
    assert "mark-OWNERSHIP-USE restrictions" in v23
    assert "mark non-tarnishment" in v23
    assert "NEGATIVE examples" in v23
    # All prior content intact.
    assert "VERBATIM COMPLETENESS" in v23
    assert "WORKED SPAN EXAMPLES" in v23
    assert "EVERGREEN CLAUSES" in v23
    # v22 predates the v2 examples.
    v22 = CONTRACTS_SPECIALIST_PROMPT_V22
    assert "audited-financial-statement delivery" not in v22
    assert "mark-HYGIENE duties" not in v22


def test_contracts_v24_reasoning_and_format_discipline():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V23,
        CONTRACTS_SPECIALIST_PROMPT_V24,
    )

    # v24 is a strict derivation of v23: the base is untouched, the derived
    # prompt adds the reasoning-before-output duty and the metrics-aligned
    # format discipline (canonical parseable forms for the regression
    # diagnostics; format-level only — the master labels CSV never reaches
    # the model).
    assert CONTRACTS_SPECIALIST_PROMPT_V24 != CONTRACTS_SPECIALIST_PROMPT_V23
    assert CONTRACTS_SPECIALIST_PROMPT_V24.startswith(CONTRACTS_SPECIALIST_PROMPT_V23[:300])
    assert "contracts_specialist_v24" in PROMPT_VERSIONS

    v24 = CONTRACTS_SPECIALIST_PROMPT_V24
    # Reasoning duty: reason through each field's evidence BEFORE finalizing,
    # emit summary + per-field entries, produced first, never scored.
    assert "REASONING BEFORE OUTPUT" in v24
    assert "`reasoning` field of the JSON" in v24
    assert "`section_ref`" in v24
    assert "it is never part of the clause text, is never scored" in v24
    assert "reasoning: object" in v24
    # Metrics-aligned format discipline (canonical parseable forms).
    assert "canonical duration phrase" in v24
    assert "two (2) years" in v24
    assert "PLAIN currency phrase" in v24
    assert "regression error" in v24
    # No leakage: the prompt never names the master-labels source.
    assert "master" not in v24.lower()
    # Commentary ban now scoped to outside the reasoning field.
    assert "never emit commentary outside the `reasoning` field" in v24
    # Rule numbering stays sequential after the insert (4 reasoning,
    # 5 format, 9 truncation) and ALL prior content is intact.
    assert "4. REASONING BEFORE OUTPUT" in v24
    assert "5. FORMAT DISCIPLINE" in v24
    assert "9. TRUNCATION-AWARE COMPLETENESS" in v24
    assert "VERBATIM COMPLETENESS" in v24
    assert "NEGATIVE examples" in v24
    # v23 predates the reasoning duty and format rules.
    v23 = CONTRACTS_SPECIALIST_PROMPT_V23
    assert "REASONING BEFORE OUTPUT" not in v23
    assert "canonical duration phrase" not in v23
    assert "never emit commentary outside" not in v23


def test_contracts_v25_additive_term_length_prefix():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V24,
        CONTRACTS_SPECIALIST_PROMPT_V25,
    )

    # v25 is a strict derivation of v24 fixing the containment regression
    # flagged on KANBAN-016: the canonical duration phrase is an ADDITIVE
    # prefix — the full verbatim clause (opener first) must follow; the
    # model must never start the quote at the duration phrase (the CUAD
    # ground-truth span is often the clause's OPENING fragment).
    assert CONTRACTS_SPECIALIST_PROMPT_V25 != CONTRACTS_SPECIALIST_PROMPT_V24
    assert CONTRACTS_SPECIALIST_PROMPT_V25.startswith(CONTRACTS_SPECIALIST_PROMPT_V24[:300])
    assert "contracts_specialist_v25" in PROMPT_VERSIONS

    v25 = CONTRACTS_SPECIALIST_PROMPT_V25
    assert "ADDITIVE and NEVER replaces the clause's own" in v25
    assert "NEVER start the quote at the duration phrase" in v25
    assert "NEVER drop, reorder, or abridge the clause opener" in v25
    assert "often the clause's OPENING fragment" in v25
    assert "EXAMPLE — for a clause reading" in v25
    # The rest of the v24 content is intact (reasoning duty, formats).
    assert "REASONING BEFORE OUTPUT" in v25
    assert "PLAIN currency phrase" in v25
    # v24 predates the additive-prefix clarification.
    v24 = CONTRACTS_SPECIALIST_PROMPT_V24
    assert "ADDITIVE and NEVER replaces" not in v24
    assert "clause opener" not in v24


def test_contracts_v26_no_template_leakage():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V25,
        CONTRACTS_SPECIALIST_PROMPT_V26,
    )

    # v26 kills the v25 worked-example TEMPLATE LEAKAGE: the verbatim example
    # clause made the model copy its sentence structure into documents with
    # DIFFERENT openers (Ritter "The initial term...", Phasebio "The term of
    # this Agreement (the "Term")..."). v26 shows openers as short variants
    # the model must match to THIS document's wording, and forbids reusing
    # the instructions' wording.
    assert CONTRACTS_SPECIALIST_PROMPT_V26 != CONTRACTS_SPECIALIST_PROMPT_V25
    assert CONTRACTS_SPECIALIST_PROMPT_V26.startswith(CONTRACTS_SPECIALIST_PROMPT_V25[:300])
    assert "contracts_specialist_v26" in PROMPT_VERSIONS

    v26 = CONTRACTS_SPECIALIST_PROMPT_V26
    assert "ADDITIVE and NEVER replaces the clause's own" in v26
    assert "NEVER start the quote at the duration phrase" in v26
    assert "says in THIS document" in v26
    assert "The initial term of this Agreement shall commence..." in v26
    assert 'The term of this Agreement (the "Term") will' in v26
    assert "never reuse wording from these instructions" in v26
    # The full verbatim worked example is GONE — that was the leakage vector.
    assert "EXAMPLE — for a clause reading" not in v26
    assert "shall remain effective for two (2) years from and after the" not in v26
    v25 = CONTRACTS_SPECIALIST_PROMPT_V25
    assert "EXAMPLE — for a clause reading" in v25
    assert "never reuse wording from these instructions" not in v25


def test_contracts_v27_multi_item_family_sections():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V26,
        CONTRACTS_SPECIALIST_PROMPT_V27,
    )

    # v27 = v26 + ONE rule (KANBAN-004): family SECTIONS are multi-item. The
    # v22/v23 50-doc runs + the v23-v26 sample5 series all show the same
    # key_obligations cluster — the model quotes ONE sentence per family
    # section while the GT holds 3-10 DISTINCT requirement sentences from it
    # (sim-matrix classification: ~60-70% of misses are NEAR, sim 0.35-0.59,
    # e.g. Ritter emitted insurance-procurement but not primary-of-all-
    # purposes/additional-insured; ~0 of the audit section's 10 GT spans).
    assert CONTRACTS_SPECIALIST_PROMPT_V27 != CONTRACTS_SPECIALIST_PROMPT_V26
    assert CONTRACTS_SPECIALIST_PROMPT_V27.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V26[:300]
    )
    assert "contracts_specialist_v27" in PROMPT_VERSIONS

    v27 = CONTRACTS_SPECIALIST_PROMPT_V27
    # The multi-item family-section rule is present and explicit.
    assert "A FAMILY SECTION IS MULTI-ITEM" in v27
    assert "EACH distinct requirement sentence is its OWN item" in v27
    assert "3-10 spans from ONE insurance, audit/records, license" in v27
    assert "primary-of-all-purposes sentence" in v27
    assert "NEVER collapse a section into its first or most prominent sentence" in v27
    assert "INCOMPLETE — go back and emit the remaining requirement sentences" in v27
    # The rule sits inside the EXHAUSTIVENESS paragraph of the v10 family
    # catalog, so the family scope is untouched (only listed families count).
    assert "EXHAUSTIVENESS WITHIN THE FAMILIES" in v27
    assert "belonging to a listed family" in v27
    # Unchanged v26 discipline: term_length opener variants + no leakage,
    # reasoning trace, formats.
    assert "never reuse wording from these instructions" in v27
    assert "says in THIS document" in v27
    assert "REASONING BEFORE OUTPUT" in v27
    assert "PLAIN currency phrase" in v27
    # v26 predates the rule.
    v26 = CONTRACTS_SPECIALIST_PROMPT_V26
    assert "A FAMILY SECTION IS MULTI-ITEM" not in v26


def test_contracts_v28_multi_item_sharpened():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V27,
        CONTRACTS_SPECIALIST_PROMPT_V28,
    )

    # v28 = v27 + two trace lessons from the v27 A/B (chunked pair: v27
    # 0.9535 vs v26 0.8944; residuals were Ritter -1 span and a Cardax
    # precision drop from definitional-fragment items): (1) only OPERATIVE
    # requirement sentences are items — definitional sentences ("any X
    # Property or improvements thereto which are used...") never are;
    # (2) the completion re-scan only ADDS items, never removes/replaces.
    assert CONTRACTS_SPECIALIST_PROMPT_V28 != CONTRACTS_SPECIALIST_PROMPT_V27
    assert CONTRACTS_SPECIALIST_PROMPT_V28.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V27[:300]
    )
    assert "contracts_specialist_v28" in PROMPT_VERSIONS

    v28 = CONTRACTS_SPECIALIST_PROMPT_V28
    assert "A FAMILY SECTION IS MULTI-ITEM" in v28
    assert "EACH distinct requirement sentence is its OWN item" in v28
    assert "NEVER collapse a section into its first or most prominent sentence" in v28
    # The sharpening: operative-vs-definitional criterion + additive re-scan.
    assert "A requirement sentence is OPERATIVE language" in v28
    assert "A DEFINITIONAL or descriptive" in v28
    assert "NEVER an item" in v28
    assert "RE-SCAN every family-" in v28
    assert "the re-scan only ADDS items" in v28
    assert "never removes or replaces one" in v28
    # v27 predates the sharpening; v26 predates the whole rule.
    v27 = CONTRACTS_SPECIALIST_PROMPT_V27
    assert "NEVER an item" not in v27
    assert "the re-scan only ADDS items" not in v27
    # Unchanged discipline: family scope, term_length, reasoning, formats.
    assert "belonging to a listed family" in v28
    assert "never reuse wording from these instructions" in v28
    assert "REASONING BEFORE OUTPUT" in v28
    assert "PLAIN currency phrase" in v28


def test_contracts_v29_coc_definition_carveout():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V28,
        CONTRACTS_SPECIALIST_PROMPT_V29,
    )

    # v29 = v28 + ONE refinement: per-span diff on the 4 regressed 50-doc docs
    # found a rule-driven regression — v28's "X means ... is NEVER an item"
    # suppressed the Change-of-Control DEFINITION spans on Ediets (1.00 ->
    # 0.45/0.40), but the CoC family's clause text IS its definition (corpus:
    # 3 of 121 CoC docs are definitional). The carve-out restores family
    # definitions as items while keeping section-glossary fragments excluded.
    assert CONTRACTS_SPECIALIST_PROMPT_V29 != CONTRACTS_SPECIALIST_PROMPT_V28
    assert CONTRACTS_SPECIALIST_PROMPT_V29.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V28[:300]
    )
    assert "contracts_specialist_v29" in PROMPT_VERSIONS

    v29 = CONTRACTS_SPECIALIST_PROMPT_V29
    assert "A DEFINITIONAL sentence is an" in v29
    assert "item ONLY when the definition itself is the family clause" in v29
    assert 'the Change of' in v29 and 'Control' in v29
    assert "such definitions ARE items" in v29
    # Glossary fragments remain excluded.
    assert "Definitional fragments that describe a" in v29
    assert "defined term's COMPONENTS" in v29
    assert "are NEVER items" in v29
    # The broad v28 phrasing is gone; v28 predates the carve-out.
    v28 = CONTRACTS_SPECIALIST_PROMPT_V28
    assert "A DEFINITIONAL or descriptive" in v28
    assert "A DEFINITIONAL sentence is an" not in v28
    assert "item ONLY when the definition itself is the family clause" not in v28


def test_contracts_v30_chunk_mode_scalar_quoting():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V29,
        CONTRACTS_SPECIALIST_PROMPT_V30,
    )

    # v30 = v29 + ONE rule closing the chunked-mode x term_length gap: chunked
    # v26 collapsed term_length on all three term docs (Ritter prefix-only
    # "five (5) years" 1.0->0.1765; Phasebio null 1.0->0.0; Ediets opener
    # dropped 1.0->0.3333) because CHUNK DUTY's "quote the VISIBLE operative
    # language faithfully and stop at what you can see" licensed the
    # relaxation. v30: scalar fields keep their exact quoting rules in every
    # chunk; prefix-only or null term_length with the clause visible is a miss.
    assert CONTRACTS_SPECIALIST_PROMPT_V30 != CONTRACTS_SPECIALIST_PROMPT_V29
    assert CONTRACTS_SPECIALIST_PROMPT_V30.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V29[:300]
    )
    assert "contracts_specialist_v30" in PROMPT_VERSIONS

    v30 = CONTRACTS_SPECIALIST_PROMPT_V30
    assert "SCALAR fields keep" in v30
    assert "their exact field rules IN EVERY CHUNK" in v30
    assert "the FULL verbatim clause, opener first" in v30
    assert "prefix-" in v30 and "never acceptable" in v30
    assert "a null" in v30 and "is a MISS" in v30
    assert "visible portion including its opener" in v30
    # Chunk duty + term_length discipline both intact; v29 predates the rule.
    assert "CHUNK DUTY" in v30
    assert "canonical duration phrase" in v30
    v29 = CONTRACTS_SPECIALIST_PROMPT_V29
    assert "SCALAR fields keep" not in v29


def test_contracts_v31_token_efficiency_refactor():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V30,
        CONTRACTS_SPECIALIST_PROMPT_V31,
    )

    # v31 = v30 with the SAME operative rules, compressed (KANBAN-021, GEPA
    # efficiency): the v23 worked-example block (2810 chars of verbatim
    # quotes) is distilled into one-line family-boundary guidance, and the
    # EXHAUSTIVENESS/RE-SCAN/VERBATIM/SIZE-CALIBRATION boilerplate is merged
    # with its overlapping neighbours — 2679 chars (-8.0%) with every
    # operative constraint preserved.
    assert CONTRACTS_SPECIALIST_PROMPT_V31 != CONTRACTS_SPECIALIST_PROMPT_V30
    assert CONTRACTS_SPECIALIST_PROMPT_V31.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V30[:300]
    )
    assert "contracts_specialist_v31" in PROMPT_VERSIONS

    v30 = CONTRACTS_SPECIALIST_PROMPT_V30
    v31 = CONTRACTS_SPECIALIST_PROMPT_V31
    assert len(v31) < len(v30) * 0.93, "compression must exceed 7%"
    # Distilled guidance replaces the verbatim worked-example quotes.
    assert "audited-financial-statement" in v31
    assert "mark-OWNERSHIP-USE restrictions" in v31
    assert '"ISO shall make available' not in v31
    assert "Fox will remit all VGSL" not in v31
    assert "NEGATIVE examples" not in v31
    # Every operative constraint survives.
    for probe in (
        "The families (mirroring the CUAD clause categories",
        "A FAMILY SECTION IS MULTI-ITEM",
        "item ONLY when the definition itself is the family clause",
        "the re-scan only ADDS items",
        "SCALAR fields keep",
        "never reuse wording from these instructions",
        "REASONING BEFORE OUTPUT",
        "PLAIN currency phrase",
        "scan BOTH sides",
        "never fabricate",
        "10-25 words",
        "Output strict JSON only",
    ):
        assert probe in v31, probe
    # The 15-word grain example stays (short, load-bearing).
    assert "Licensee shall not sublicense, sell, or" in v31


def test_contracts_v32_effective_date_convention_fix():
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V31,
        CONTRACTS_SPECIALIST_PROMPT_V32,
    )

    # v32 = v31 + ONE rule (KANBAN-029, full-corpus diagnosis on the v31@510
    # reasoning-trace corpus): the v12-era effective_date tie-break said "the
    # defined term wins" when both an Agreement Date and a defined Effective
    # Date appear, but CUAD maps BOTH onto the field and holds the
    # AGREEMENT/EXECUTION date as answers[0] in 493/493 docs. On the 26
    # differing-date docs that pushes the model to emit the wrong date (6 at
    # 0.0 + 14 partial) and feeds 23 null-when-date-present docs (field
    # 0.8577 @510, 51/509 at 0.0). Corrected rule: the AGREEMENT/EXECUTION
    # date wins whenever one is stated; a defined "Effective Date" term is
    # fallback only when no execution date appears; never null with a stated
    # date visible.
    assert CONTRACTS_SPECIALIST_PROMPT_V32 != CONTRACTS_SPECIALIST_PROMPT_V31
    assert CONTRACTS_SPECIALIST_PROMPT_V32.startswith(
        CONTRACTS_SPECIALIST_PROMPT_V31[:300]
    )
    assert "contracts_specialist_v32" in PROMPT_VERSIONS

    v31 = CONTRACTS_SPECIALIST_PROMPT_V31
    v32 = CONTRACTS_SPECIALIST_PROMPT_V32
    # The new convention rule is present; the v12-era "defined term wins"
    # tie-break is gone from v32 (but intact in the untouched v31 base).
    assert "the AGREEMENT/EXECUTION date" in v32
    assert "holds the AGREEMENT/EXECUTION date as the value" in v32
    assert "used ONLY when no execution/agreement date is stated" in v32
    assert "never the defined term" in v32
    assert "NEVER output null when a stated date appears" in v32
    assert 'the defined term wins' not in v32
    assert "when both appear, output the date the agreement takes effect" not in v32
    # Predecessor stays intact — only ONE effective_date field rule exists.
    assert 'the defined term wins' in v31
    assert v32.count("`effective_date`") == 1
    assert "ISO format per the format rules below" in v32


def test_contracts_v33_reasoning_trace_retag():
    """v33 retags obligation reasoning entries with canonical CUAD category
    names (issue #21 / KANBAN-051): the umbrella 'key_obligations' tag is
    forbidden and the misspelling guard is present."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V32,
        CONTRACTS_SPECIALIST_PROMPT_V33,
    )

    # v33 is a strict derivation of v32: base untouched, only the retag rule added.
    assert "contracts_specialist_v33" in PROMPT_VERSIONS
    assert CONTRACTS_SPECIALIST_PROMPT_V33 != CONTRACTS_SPECIALIST_PROMPT_V32
    assert CONTRACTS_SPECIALIST_PROMPT_V33.startswith(CONTRACTS_SPECIALIST_PROMPT_V32[:300])

    v33 = CONTRACTS_SPECIALIST_PROMPT_V33
    # The retag rule: canonical CUAD category name, never the umbrella.
    assert "RETAG RULE" in v33
    assert "CANONICAL CUAD CATEGORY" in v33
    assert 'NEVER the umbrella' in v33 and '"key_obligations"' in v33
    assert "key_obbligations" in v33  # the misspelling is explicitly guarded
    # The canonical vocabulary is enumerated.
    assert '"Anti-Assignment"' in v33
    assert '"Volume Restriction"' in v33
    assert '"Audit Rights"' in v33
    assert '"Cap On Liability"' in v33
    assert "Third Party Beneficiary" in v33
    assert "ONE entry per DISTINCT obligation clause" in v33
    # The schema description carries the retag semantics too.
    assert "obligation entries' `field` is the canonical CUAD category name" in v33
    # Predecessor stays intact.
    assert "RETAG RULE" not in CONTRACTS_SPECIALIST_PROMPT_V32


def test_contracts_v34_anti_collapse_rules():
    """v34 (KANBAN-054) adds the three anti-collapse rules to v33 without
    touching the retag schema or any earlier rule: R1 field-presence
    self-check, R2 category-level completeness over the 32 canonical CUAD
    categories, R3 verbatim quoting at the GT span grain."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V33,
        CONTRACTS_SPECIALIST_PROMPT_V34,
    )

    # v34 is a strict derivation of v33: base untouched, rules added on top.
    assert "contracts_specialist_v34" in PROMPT_VERSIONS
    assert CONTRACTS_SPECIALIST_PROMPT_V34 != CONTRACTS_SPECIALIST_PROMPT_V33
    assert CONTRACTS_SPECIALIST_PROMPT_V34.startswith(CONTRACTS_SPECIALIST_PROMPT_V33[:300])

    v34 = CONTRACTS_SPECIALIST_PROMPT_V34
    # R1 — field-presence self-check: no field may be null when visible.
    assert "FIELD-PRESENCE SELF-CHECK" in v34
    assert "contract_value" in v34 and "renewal_terms" in v34
    assert "never null when a" in v34
    assert "The self-check ADDS values only" in v34
    # R2 — category-level completeness: the checklist over the canonical list.
    assert "CATEGORY-LEVEL COMPLETENESS" in v34
    assert "a category is NEVER collapsed" in v34
    assert "ZERO tagged entries" in v34 and "ADDING to the list only" in v34
    assert "never fabricate" in v34
    # The v33 canonical vocabulary stays intact inside the checklist rule.
    assert '"Anti-Assignment"' in v34
    assert "Third Party Beneficiary" in v34
    # R3 — verbatim fidelity at the GT span grain.
    assert "WORD-FOR-WORD" in v34
    assert "a paraphrase, restatement, or condensed" in v34
    assert "never by rewording what remains" in v34
    # The retag schema description survives v34 unchanged.
    assert "obligation entries' `field` is the canonical CUAD category name" in v34
    for rule in ("FIELD-PRESENCE SELF-CHECK", "CATEGORY-LEVEL COMPLETENESS",
                 "WORD-FOR-WORD", "a category is NEVER collapsed"):
        assert rule not in CONTRACTS_SPECIALIST_PROMPT_V33


def test_contracts_v35_item_level_category_split():
    """v35 (KANBAN-055) closes the third anti-collapse mode: the ITEM-LEVEL
    category split that v34's R1 (field presence) and R2 (category completeness)
    do not cover. A single key_obligations item holding TWO different
    canonical categories' duties must be split into one entry per duty, each
    tagged with its exact category (never a sibling / family / generic label)."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V34,
        CONTRACTS_SPECIALIST_PROMPT_V35,
    )

    # v35 is a strict append-style derivation of v34 (base untouched), registered.
    assert "contracts_specialist_v35" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracts_specialist_v35"] is CONTRACTS_SPECIALIST_PROMPT_V35
    assert CONTRACTS_SPECIALIST_PROMPT_V35 != CONTRACTS_SPECIALIST_PROMPT_V34
    assert CONTRACTS_SPECIALIST_PROMPT_V35.startswith(CONTRACTS_SPECIALIST_PROMPT_V34[:300])

    v35 = CONTRACTS_SPECIALIST_PROMPT_V35
    # The item-level split: one entry per distinct category's duty.
    assert "ITEM-LEVEL CATEGORY GUARD" in v35
    assert "one key_obligations entry per DISTINCT" in v35
    assert "CATEGORY's duty" in v35
    assert "two different" in v35 and "canonical" in v35
    assert "single merged item" in v35
    # Exact-category tagging: no sibling / no family-group collapse.
    assert "'No-Solicit Of Customers' is not" in v35
    assert "'No-Solicit Of Employees'" in v35
    assert "'Cap On Liability' is not" in v35
    assert "a license grant is not generic 'IP'" in v35
    # The example grounds the split (Anti-Assignment / Non-Disparagement).
    assert "Anti-Assignment" in v35 and "Non-Disparagement" in v35
    # opencode's v34 anti-collapse rules are preserved inside v35 (R1/R2/R3).
    assert "FIELD-PRESENCE SELF-CHECK" in v35
    assert "CATEGORY-LEVEL COMPLETENESS" in v35
    assert "WORD-FOR-WORD" in v35
    # Predecessor stays intact: no item-level guard in v34.
    assert "ITEM-LEVEL CATEGORY GUARD" not in CONTRACTS_SPECIALIST_PROMPT_V34


def test_contracts_v36_full_sentence_grain():
    """v36 (KANBAN-056) reconciles the span-grain rule_contradiction that
    v34/v35 inherited from the v10-era fragment rules: the prompt told the
    model to quote 10-25-word ATOMIC FRAGMENTS while R3 demanded verbatim
    full-span quotes. Measured on the 255-doc half-corpus (v34/v35 A/B):
    146 of 448 near-miss key_obligations labels were PURE TRUNCATIONS (the
    predicted item was a head-prefix of the GT sentence) and 16/208
    term_length expectations were duration-only quotes — the model followed
    the concrete fragment instruction. v36 replaces every fragment-grain
    instruction with full-clause-sentence grain, guards term_length against
    duration-only output, and adds the effective_date blank-placeholder
    carve-out (a fabricated fill of "April __, 2005" scores 0 while null
    satisfies the blank expectation)."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V34,
        CONTRACTS_SPECIALIST_PROMPT_V35,
        CONTRACTS_SPECIALIST_PROMPT_V36,
    )

    # v36 is a strict append-style derivation of v35 (base untouched), registered.
    assert "contracts_specialist_v36" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracts_specialist_v36"] is CONTRACTS_SPECIALIST_PROMPT_V36
    assert CONTRACTS_SPECIALIST_PROMPT_V36 != CONTRACTS_SPECIALIST_PROMPT_V35
    assert CONTRACTS_SPECIALIST_PROMPT_V36.startswith(CONTRACTS_SPECIALIST_PROMPT_V35[:300])

    v36 = CONTRACTS_SPECIALIST_PROMPT_V36
    # (1) The grain reconciliation: full-clause-sentence grain replaces every
    # fragment-grain relic (the rule_contradiction is gone, not just softened).
    assert "FULL CLAUSE SENTENCES, quoted verbatim and in" in v36
    assert "the ground-truth labels are the annotator's stored clause" in v36
    assert "Matching is by token" in v36 and "containment" in v36
    assert "Never emit a truncated sentence" in v36
    for relic in ("ATOMIC FRAGMENTS", "10-25-word", "as its OWN fragment",
                  "STRIP sentence preamble", "Quote each fragment"):
        assert relic not in v36
        assert relic in CONTRACTS_SPECIALIST_PROMPT_V35  # v35 base untouched
    assert "signals\n     missed spans: split them" in CONTRACTS_SPECIALIST_PROMPT_V35
    assert "signals missed spans" not in v36
    assert "full-sentence span grain" in v36
    assert "split MERGED MULTI-SENTENCE items" in v36
    # (2) The v35 item-level guard survives but is re-cast at full-sentence
    # grain (its old fragment-quoting phrase is gone — no contradiction).
    assert "ITEM-LEVEL CATEGORY GUARD" in v36
    assert "FULL clause sentence(s) verbatim in its own item" in v36
    assert "quote the operative words of that duty" not in v36
    # (3) term_length duration-only guard.
    assert "A quote consisting of ONLY the duration phrase" in v36
    assert "The full term" in v36 and "ALWAYS follow the prefix" in v36
    # (4) effective_date blank-placeholder carve-out.
    assert "BLANK PLACEHOLDER" in v36
    assert "never a fabricated fill" in v36
    assert "null satisfies the blank expectation" in v36
    # (5) v34's anti-collapse rules survive inside v36.
    assert "FIELD-PRESENCE SELF-CHECK" in v36
    assert "CATEGORY-LEVEL COMPLETENESS" in v36
    assert "WORD-FOR-WORD" in v36


def test_contracts_v37_payment_monetary_capture():
    """v37 (KANBAN-056 — GEPA crossover built on v36's WIN, frozen design in
    docs/memos/contracts_specialist_v37_design.md) adds the payment/monetary capture
    + canonical tag discipline rule. Measured on the 255-doc half-corpus (v34
    record + master GT CSV): payment families are 297 of 801 (37%) of the
    present-but-untagged (doc, category) pairs — Price Restrictions 0/9 tagged
    (+24 fp), Uncapped Liability 1/46, Volume Restriction 3/35; 78/255 docs
    collapse all key_obligations items under one field-level reasoning tag
    (115 of the 297 misses; 50/78 of those docs contain emitted-but-untagged
    money items); contract_value is never GT (0/255 expected) but null on
    113/255 docs that carry payment GT. v37 = v36 + 4 surgical .replace()
    edits (base byte-identical, registered): the PAYMENT TERMS & MONETARY
    CLAUSES scan family (10 money-clause shapes at v36's full-sentence grain),
    the canonical tag discipline (never a field-level `key_obligations`
    entry), the contract_value trigger extension (payment schedule / per-unit
    fee or royalty / minimum commitment = visible consideration), and the
    Uncapped/Liquidated enumeration appends."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V36,
        CONTRACTS_SPECIALIST_PROMPT_V37,
    )

    # v37 is a strict derivation of v36 (base untouched), registered.
    assert "contracts_specialist_v37" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracts_specialist_v37"] is CONTRACTS_SPECIALIST_PROMPT_V37
    assert CONTRACTS_SPECIALIST_PROMPT_V37 != CONTRACTS_SPECIALIST_PROMPT_V36
    assert CONTRACTS_SPECIALIST_PROMPT_V37.startswith(CONTRACTS_SPECIALIST_PROMPT_V36[:300])

    v37 = CONTRACTS_SPECIALIST_PROMPT_V37
    # (1) The payment scan family — all 10 money-clause shapes + measured examples.
    assert "PAYMENT TERMS & MONETARY CLAUSES" in v37
    assert "mandatory scan family" in v37
    for shape in ("Revenue/Profit Sharing:", "Minimum Commitment:", "Volume Restriction:",
                  "Price Restrictions:", "Liquidated Damages:", "Cap On Liability:",
                  "Uncapped Liability:", "Insurance:", "Most Favored Nation:",
                  "Post-Termination Services:"):
        assert shape in v37
    assert "Specified Royalty Percentage of all revenues received" in v37
    assert "thirty percent (30%) of the Net Sales in excess of Eleven" in v37
    assert "not less than $1 million per occurrence" in v37
    assert "nothing in this Agreement shall limit" in v37
    assert "A fee or payment amount alone is NOT a price restriction" in v37
    # (2) Canonical tag discipline: no field-level fallback, no sibling tags.
    assert "never a field-level `key_obligations` entry" in v37
    assert "a royalty is Revenue/Profit Sharing, NOT License Grant" in v37
    assert "an insurance limit is Insurance, not Cap On Liability" in v37
    assert "EXACT canonical category tag" in v37
    assert "78 of 255 documents fell back to a single field-level tag" in v37
    assert "ZERO tagged entries is INCOMPLETE" in v37
    # (3) contract_value trigger extension (rule 10).
    assert "A payment SCHEDULE" in v37 and "First Contract Year" in v37
    assert "a per-unit fee or royalty" in v37
    assert "113 of 255 docs carried payment clauses with contract_value null" in v37
    # (4) Uncapped + Liquidated enumeration appends.
    assert "Add the un-limited shapes" in v37
    assert "only 1 of" in v37 and "46 present Uncapped Liability" in v37
    assert "Add the amount shapes" in v37
    # (5) v36 base preserved byte-for-byte (grain language intact inside v37).
    assert "FULL CLAUSE SENTENCES, quoted verbatim and in" in v37
    assert "full-sentence span grain" in v37
    assert "A quote consisting of ONLY the duration phrase" in v37
    assert "BLANK PLACEHOLDER" in v37
    assert "CATEGORY-LEVEL COMPLETENESS" in v37
    assert "FIELD-PRESENCE SELF-CHECK" in v37
    # v36 does NOT contain the v37 additions (they are new, not inherited).
    v36 = CONTRACTS_SPECIALIST_PROMPT_V36
    for relic in ("PAYMENT TERMS & MONETARY CLAUSES", "never a field-level `key_obligations` entry",
                  "A payment SCHEDULE", "Add the un-limited shapes", "Add the amount shapes",
                  "A fee or payment amount alone is NOT a price restriction"):
        assert relic not in v36


def test_contracts_v38_sparse_family_shapes():
    """v38 (KANBAN-057 — next F1 mutation on v36's WIN, v36 base byte-identical)
    completes the sparse-family shapes + adds a named re-scan duty. Measured on
    the 255-doc half-corpus (v36 record + master GT CSV, KPI-level fn
    decomposition over 1686 positive pairs): v36 FN = 1319 of which 536 are
    ABSENT (no quoted span with >=0.7 token coverage of the GT clause) — 44% of
    all misses; the absent mass sits in families the model never quotes:
    Post-Termination Services 55, Anti-Assignment 43, Cap On Liability 43,
    Minimum Commitment 37, License Grant 33, Warranty Duration 32 (absent from
    the prompt entirely), Competitive Restriction Exception 29 + Volume
    Restriction 29 (guard-list names but NO shape entries), Revenue/Profit
    Sharing 31, Covenant Not To Sue 25, Liquidated Damages 22, Non-Transferable
    License 20. The generic R2 checklist does not fire for the shape-complete
    families (Covenant/Post-Termination/Liquidated stay absent-heavy), so the
    fix is a NAMED re-scan. v38 = v36 + 2 surgical .replace() edits: entries
    27-29 (Warranty Duration, Competitive Restriction Exception, Volume
    Restriction — shapes drawn from real GT clauses) + the UNDER-QUOTED FAMILY
    RE-SCAN sentence in the R2 completeness block."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V36,
        CONTRACTS_SPECIALIST_PROMPT_V38,
    )

    # v38 is a strict derivation of v36 (base untouched), registered.
    assert "contracts_specialist_v38" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracts_specialist_v38"] is CONTRACTS_SPECIALIST_PROMPT_V38
    assert CONTRACTS_SPECIALIST_PROMPT_V38 != CONTRACTS_SPECIALIST_PROMPT_V36
    assert CONTRACTS_SPECIALIST_PROMPT_V38.startswith(CONTRACTS_SPECIALIST_PROMPT_V36[:300])

    v38 = CONTRACTS_SPECIALIST_PROMPT_V38
    # (1) The 3 new enumeration entries with their shape language.
    assert "27. Warranty Duration:" in v38
    assert "warranty-period clauses and their commencement" in v38
    assert "The warranty period for each Product is specified in the Price List" in v38
    assert "32 of 32" in v38 and "present Warranty Duration clauses were never quoted" in v38
    assert "28. Competitive Restriction Exception:" in v38
    assert "carve-outs or exceptions to" in v38
    assert "Notwithstanding the foregoing, this provision shall not prevent" in v38
    assert "39 of 39 present clauses never quoted despite the guard-list name" in v38
    assert "29. Volume Restriction:" in v38
    assert "quantity, volume, or amount ceilings" in v38
    assert "The total value of the returned Products" in v38
    assert "35 of 39" in v38 and "present clauses never quoted" in v38
    # (2) The named re-scan duty in the R2 completeness block.
    assert "UNDER-QUOTED FAMILY RE-SCAN" in v38
    assert "536 of 1686 positive pairs" in v38
    for fam in ("Warranty Duration", "Competitive Restriction", "Volume Restriction",
                "Covenant Not To Sue", "Post-Termination Services", "Liquidated Damages",
                "license variants (Non-Transferable,",
                "ROFR/ROFO/ROFN", "Joint Ip"):
        assert fam in v38
    # (3) The re-scan preserves the fabrication guard + ADDING-only discipline.
    assert "never fabricate" in v38
    assert "ADDING to the list only" in v38
    # (4) v36 base preserved byte-for-byte (grain language intact inside v38).
    assert "FULL CLAUSE SENTENCES, quoted verbatim and in" in v38
    assert "full-sentence span grain" in v38
    assert "A quote consisting of ONLY the duration phrase" in v38
    assert "CATEGORY-LEVEL COMPLETENESS" in v38
    assert "FIELD-PRESENCE SELF-CHECK" in v38
    # v36 does NOT contain the v38 additions (they are new, not inherited).
    v36 = CONTRACTS_SPECIALIST_PROMPT_V36
    for relic in ("27. Warranty Duration:", "28. Competitive Restriction Exception:",
                  "29. Volume Restriction:", "UNDER-QUOTED FAMILY RE-SCAN",
                  "536 of 1686 positive pairs"):
        assert relic not in v36


def test_contracts_v39_payment_fold_precision_and_completion():
    """contracts_specialist_v39 (KANBAN-059) = the maximize-everything
    crossover: derivation chain v36 -> v37 -> v39 (v37 embeds the payment
    fold; v39 = v37 + precision guard + within-category completion), each
    part ONE lesson, base constants byte-identical.

    Motivation (255-doc half-corpus, CORRECTED scorer — whitespace-collapse +
    <omitted>-stripping landed in load_master_gt, all records re-scored):
    v37 leads every recall-side metric (F1 0.4170 / F2 0.3382 / R 0.3004 /
    P 0.6820 / J 0.4981 / false-nr 0.3260 vs v36 F1 0.4073 / F2 0.3243 /
    R 0.2855 / P 0.7107) but the per-doc paired gate is inside the band
    (v37: +25 TP at +40 FP). FP audit: Termination For Convenience = 53 fp
    (largest fp category — term-of-agreement clauses and for-cause/default/
    discontinuation terminations tagged as convenience; the category has NO
    enumeration entry, only a guard-list name); Uncapped Liability +5 fp
    (fee/royalty "CAPs" tagged as liability caps); Revenue/Profit Sharing
    +6 fp (service fees, cost-sharing). Recall decomposition: 35% of positive
    pairs carry MULTIPLE GT clause sentences and 556 of 1,678 positives fail
    the verbatim predicate with one or more of the category's sentences never
    quoted (NETGEAR Insurance 3 clauses/2 quoted, Cap On Liability 9/3;
    63 more fail by dropping the sentence's leading phrase)."""
    from src.prompts import (
        CONTRACTS_SPECIALIST_PROMPT_V36,
        CONTRACTS_SPECIALIST_PROMPT_V37,
        CONTRACTS_SPECIALIST_PROMPT_V39,
    )

    # Registration + derivation chain (v37 under v39 byte-identical; v36 under v37).
    assert "contracts_specialist_v39" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracts_specialist_v39"] is CONTRACTS_SPECIALIST_PROMPT_V39
    assert CONTRACTS_SPECIALIST_PROMPT_V39 != CONTRACTS_SPECIALIST_PROMPT_V37
    assert CONTRACTS_SPECIALIST_PROMPT_V39.startswith(CONTRACTS_SPECIALIST_PROMPT_V37[:300])
    assert CONTRACTS_SPECIALIST_PROMPT_V37.startswith(CONTRACTS_SPECIALIST_PROMPT_V36[:300])

    v39 = CONTRACTS_SPECIALIST_PROMPT_V39
    v37 = CONTRACTS_SPECIALIST_PROMPT_V37
    # (1) Part (a) — the payment fold is inherited from v37.
    assert "PAYMENT TERMS & MONETARY CLAUSES" in v39
    assert "never a field-level `key_obligations` entry" in v39
    assert "a royalty is Revenue/Profit Sharing, NOT License Grant" in v39
    assert 'a "for the sum of" phrase' in v39
    assert "A payment SCHEDULE" in v39
    assert "the un-limited shapes" in v39
    assert "the amount shapes" in v39
    # (2) Part (b) — precision guard: the new enumeration entry 27 with the
    #     termination boundary shape (53 of 71 TFC outputs were fp).
    assert "27. Termination For Convenience:" in v39
    assert "termination by either party WITHOUT\n         CAUSE" in v39
    assert "may be terminated at any time without cause" in v39
    assert "NEVER these: term-of-agreement or" in v39
    assert "termination for\n         default, breach, insolvency, or cause" in v39
    assert "53 of 71 Termination For Convenience outputs are\n         false positives" in v39
    # (2b) Part (b) — the money-family boundary clarifications in the R2 block.
    assert "a CAP on fees, royalties,\n   or prices is NOT a liability cap" in v39
    assert "fees for services, cost reimbursements, and expense sharing are\n   NOT Revenue/Profit Sharing" in v39
    assert "price-change NOTICE duty" in v39
    assert "is not a Price Restriction unless it caps amounts or\n   frequency" in v39
    # (3) Part (c) — within-category completion: grain-rule append + R2 strengthen.
    assert "WITHIN-CATEGORY\n     COMPLETION" in v39
    assert "35% of\n     positive pairs carry MULTIPLE clause sentences" in v39
    assert "556 of\n     1,678 positives failed" in v39
    assert "EVERY distinct clause sentence is quoted as\n     its own item" in v39
    assert "Quote each sentence from its FIRST WORD" in v39
    assert "never\n     drop a leading phrase" in v39
    assert "ONE item AND ONE reasoning entry PER DISTINCT CLAUSE\n   SENTENCE" in v39
    assert "INCOMPLETE until every sentence is quoted as its own item" in v39
    # (4) Guards preserved: fabrication guard, ADDING-only, verbatim grain.
    assert "never fabricate" in v39
    assert "ADDING to the list only" in v39
    assert "FULL CLAUSE SENTENCES, quoted verbatim" in v39
    assert "CATEGORY-LEVEL COMPLETENESS" in v39
    # (5) v37/v36 do NOT contain the v39 additions; v38 is NOT in the chain.
    for relic in ("27. Termination For Convenience:", "WITHIN-CATEGORY\n     COMPLETION",
                  "PER DISTINCT CLAUSE\n   SENTENCE", "a CAP on fees, royalties,\n   or prices is NOT a liability cap"):
        assert relic not in v37
        assert relic not in CONTRACTS_SPECIALIST_PROMPT_V36
    assert "27. Warranty Duration:" not in v39
    assert "UNDER-QUOTED FAMILY RE-SCAN" not in v39
    assert "28. Competitive Restriction Exception:" not in v39


def test_contracteval_v0_registered_and_verbatim():
    """contracteval_v0 (KANBAN-052) = the paper's system prompt VERBATIM and
    registered as a versioned prompt (the experiment identity for the GEPA
    iteration loop)."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_SYSTEM_PROMPT,
        CONTRACTEVAL_USER_TEMPLATE,
    )

    assert "contracteval_v0" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v0"] is CONTRACTEVAL_PROMPT_V0
    # v0 is the paper's exact system prompt (arXiv 2508.03080, open_source_model.py).
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert "extract and return only the sentence(s) from the Context" in CONTRACTEVAL_SYSTEM_PROMPT
    assert 'respond with: "No related clause."' in CONTRACTEVAL_SYSTEM_PROMPT
    assert "Do not rephrase or summarize in any way" in CONTRACTEVAL_SYSTEM_PROMPT
    # The runner-side Context:/Question: template carries the placeholders.
    assert "{context}" in CONTRACTEVAL_USER_TEMPLATE and "{question}" in CONTRACTEVAL_USER_TEMPLATE
    assert CONTRACTEVAL_USER_TEMPLATE.startswith("Context:")


def test_contracteval_v1_derived_scope_discipline():
    """contracteval_v1 (KANBAN-052 GEPA iteration 1) = v0 + ONE scope-
    discipline rule (tightest answer-stating span): derived append-style so v0
    stays byte-identical, and the "No related clause." contract is preserved.

    Motivation (full v0 run, 4,182 pairs, qwen3.7-flash): FP 919 -> precision
    0.4743 (topic-adjacent passages quoted on negative rows); Jaccard 0.5058
    with 425/829 TPs outputting >2x the GT span (Agreement Date F1 0.915 but
    J 0.129)."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_PROMPT_V1,
        CONTRACTEVAL_SYSTEM_PROMPT,
    )

    assert "contracteval_v1" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v1"] is CONTRACTEVAL_PROMPT_V1
    # Derived append-style: v0 is a strict prefix of v1 and is untouched.
    assert CONTRACTEVAL_PROMPT_V1.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert CONTRACTEVAL_PROMPT_V1 != CONTRACTEVAL_PROMPT_V0
    # The new lesson instruction is present.
    assert "Quote the smallest span of the Context that states the complete answer" in CONTRACTEVAL_PROMPT_V1
    assert "Exclude sentences that merely relate to the Question's topic without stating the answer" in CONTRACTEVAL_PROMPT_V1
    # The "No related clause." contract survives in BOTH v0 and v1.
    assert CONTRACTEVAL_PROMPT_V1.count('"No related clause."') == 2
    # Mirror faithfulness: still a plain verbatim-extraction prompt — no
    # analysis preamble, no JSON, no classification output.
    assert CONTRACTEVAL_PROMPT_V1.startswith(
        "You are an assistant with strong legal knowledge")
    assert "Do not rephrase or summarize in any way" in CONTRACTEVAL_PROMPT_V1
    for forbidden in ("JSON", "json", "reasoning", "output format", "You are an AI"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V1


def test_contracteval_v2_derived_trigger_carveout():
    """contracteval_v2 (KANBAN-052 GEPA iteration 2) = v1 + the trigger/span
    decoupling: recall carve-out on the trigger (addresses/responds-to, not
    states-the-answer) + complete-quote span rule. Derived append-style; the
    whole v0 -> v1 -> v2 chain stays byte-identical at each step, and the
    "No related clause." contract is preserved (still exactly 2 occurrences).

    Motivation (v1 A/B, identical 4,182 rows): TP->FN 118 of which only 11
    are refusals and 107 are over-trimmed fragments (34 had v0 J >= 0.9);
    false-nr rose 0.0289 -> 0.045; the 190 FP->TN wins must stay fixed."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_PROMPT_V1,
        CONTRACTEVAL_PROMPT_V2,
        CONTRACTEVAL_SYSTEM_PROMPT,
    )

    assert "contracteval_v2" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v2"] is CONTRACTEVAL_PROMPT_V2
    # Derived chain intact: v0 (paper verbatim) -> v1 -> v2, all appended.
    assert CONTRACTEVAL_PROMPT_V2.startswith(CONTRACTEVAL_PROMPT_V1)
    assert CONTRACTEVAL_PROMPT_V1.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert CONTRACTEVAL_PROMPT_V2 != CONTRACTEVAL_PROMPT_V1
    # The carve-out trigger language is present.
    assert "The following conditions replace the earlier trigger and span conditions" in CONTRACTEVAL_PROMPT_V2
    assert "relates to the Question's subject AND responds to it" in CONTRACTEVAL_PROMPT_V2
    assert "Give the no-related response only when no passage in the Context addresses the Question at all" in CONTRACTEVAL_PROMPT_V2
    # The smallest-span rule survives, completed by the never-fragment rule.
    assert "Quote the smallest span that carries the complete answer" in CONTRACTEVAL_PROMPT_V2
    assert "never a fragment of a sentence" in CONTRACTEVAL_PROMPT_V2
    assert "quote the entire sentence" in CONTRACTEVAL_PROMPT_V2
    # The "No related clause." contract: still exactly 2 occurrences (v0 + v1).
    assert CONTRACTEVAL_PROMPT_V2.count('"No related clause."') == 2
    # Mirror faithfulness: plain verbatim-extraction prompt, no JSON, no
    # thinking preamble, no classification output.
    assert CONTRACTEVAL_PROMPT_V2.startswith(
        "You are an assistant with strong legal knowledge")
    for forbidden in ("JSON", "json", "reasoning", "output format", "You are an AI"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V2


def test_contracteval_v3_derived_quote_fidelity():
    """contracteval_v3 (KANBAN-052 GEPA iteration 3) = v0 + the quote-
    fidelity rule: permissive trigger kept with v2's bounded semantics, span
    rule replaced by verbatim (character-for-character) + complete-quote
    (never a fragment) discipline. Built on V0 so the composed text carries
    NO v1/v2 refusal or element-alone vocabulary; the full v0 -> v1 -> v2
    chain stays byte-identical, and the "No related clause." contract is
    preserved (exactly 2 occurrences: v0 + the v3 block).

    Motivation (v2 3-way A/B, identical 4,182 rows): of the 160 v2-FN rows
    with a correct v0/v1 quote, 52 are whitespace-only failures and 97 are
    trims/case-changes (only 8 are refusals — the trigger was NOT the
    weakest link; quote fidelity was)."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_PROMPT_V1,
        CONTRACTEVAL_PROMPT_V2,
        CONTRACTEVAL_PROMPT_V3,
        CONTRACTEVAL_SYSTEM_PROMPT,
    )

    assert "contracteval_v3" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v3"] is CONTRACTEVAL_PROMPT_V3
    # Built on V0: v3 startswith the paper prompt; the v0->v1->v2 chain is
    # byte-identical (v3 does NOT stack on v2 — the span rule was replaced).
    assert CONTRACTEVAL_PROMPT_V3.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert CONTRACTEVAL_PROMPT_V1.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V2.startswith(CONTRACTEVAL_PROMPT_V1)
    assert CONTRACTEVAL_PROMPT_V3 != CONTRACTEVAL_PROMPT_V2
    # Permissive trigger present (v0's own + the bounded clarification).
    assert "directly address or relate to the Question" in CONTRACTEVAL_PROMPT_V3
    assert "relates to the Question's subject and responds to it" in CONTRACTEVAL_PROMPT_V3
    assert 'answer "No related clause." only when no passage in the Context addresses the Question at all' in CONTRACTEVAL_PROMPT_V3
    # Quote fidelity: verbatim + complete spans.
    assert "Quote the exact text of that span, character for character" in CONTRACTEVAL_PROMPT_V3
    assert "never clean, normalize, or re-type the text" in CONTRACTEVAL_PROMPT_V3
    assert "Quote the complete sentence(s) that carry the answer, never a fragment of a sentence" in CONTRACTEVAL_PROMPT_V3
    assert "quote the whole sentence" in CONTRACTEVAL_PROMPT_V3
    # Refusal vocabulary excised: no "states the answer", no "related but
    # different" phrasing anywhere in the composed v3.
    for forbidden in ("states the answer", "related but different",
                      "element alone is the span", "merely relate"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V3
    # "No related clause." contract: exactly 2 occurrences (v0 + v3 block).
    assert CONTRACTEVAL_PROMPT_V3.count('"No related clause."') == 2
    # Mirror faithfulness: plain verbatim-extraction prompt, no JSON, no
    # thinking preamble, no classification output.
    assert CONTRACTEVAL_PROMPT_V3.startswith(
        "You are an assistant with strong legal knowledge")
    for forbidden in ("JSON", "json", "reasoning", "output format", "You are an AI"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V3


def test_contracteval_v4_derived_verbatim_smallest_span():
    """contracteval_v4 (KANBAN-052 GEPA iteration 4 — the synthesis) = v3
    with ONE surgical replace: the doubt-bias tail ("when in doubt whether
    a fragment would omit part of the answer, quote the whole sentence") is
    replaced by the smallest-span-complete rule. Verbatim fidelity (v3's TP
    recovery engine) and the bounded trigger are kept; the whole-sentence-
    when-doubt clause that re-bloated v3 (J -0.0953 on shared rows, +208
    TN->FP) is gone. The v0 -> v1 -> v2 -> v3 chain stays byte-identical
    and the "No related clause." contract is preserved (exactly 2)."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_PROMPT_V1,
        CONTRACTEVAL_PROMPT_V2,
        CONTRACTEVAL_PROMPT_V3,
        CONTRACTEVAL_PROMPT_V4,
        CONTRACTEVAL_SYSTEM_PROMPT,
    )

    assert "contracteval_v4" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v4"] is CONTRACTEVAL_PROMPT_V4
    # Byte-identical derivation chain: v0 -> v1 -> v2 -> v3 -> v4, one
    # surgical replace only.
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert CONTRACTEVAL_PROMPT_V1.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V2.startswith(CONTRACTEVAL_PROMPT_V1)
    assert CONTRACTEVAL_PROMPT_V3.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V4.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V4 != CONTRACTEVAL_PROMPT_V3
    # The synthesis: verbatim fidelity AND smallest-complete-span, both present.
    assert "Quote the exact text of that span, character for character" in CONTRACTEVAL_PROMPT_V4
    assert "never clean, normalize, or re-type the text" in CONTRACTEVAL_PROMPT_V4
    assert "Quote the smallest span that carries the complete answer" in CONTRACTEVAL_PROMPT_V4
    assert "never a fragment of a sentence" in CONTRACTEVAL_PROMPT_V4
    assert "otherwise quote the complete sentence(s)" in CONTRACTEVAL_PROMPT_V4
    # The doubt-bias clause is ABSENT (v3's bloat driver).
    for forbidden in ("when in doubt whether a fragment would omit part of the answer",
                      "quote the whole sentence", "quote the whole passage"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V4
    # Trigger + no-related contract unchanged from v3.
    assert "relates to the Question's subject and responds to it" in CONTRACTEVAL_PROMPT_V4
    assert CONTRACTEVAL_PROMPT_V4.count('"No related clause."') == 2
    # Refusal vocabulary still absent; mirror-faithful plain prompt.
    for forbidden in ("states the answer", "related but different"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V4
    assert CONTRACTEVAL_PROMPT_V4.startswith(
        "You are an assistant with strong legal knowledge")
    for forbidden in ("JSON", "json", "reasoning", "output format", "You are an AI"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V4


def test_contracteval_v5_derived_fragment_permission():
    """contracteval_v5 (KANBAN-052 GEPA iteration 5 — the fragment
    synthesis) = v4 with ONE surgical replace: the sentence-granularity
    tail ("otherwise quote the complete sentence(s), never a fragment of a
    sentence") is deleted in favor of an explicit fragment permission —
    any contiguous run, provided it contains every word of the complete
    answer (and every part of a multi-part answer) and no more text than
    the answer needs. Verbatim fidelity (the TP engine) and the bounded
    trigger are untouched. Motivation (v4 A/B, identical 4,182 rows): the
    smallest-span rule fired only at the extremes (100 FP->TN, J 0.06->1.0
    wins) while 1,310/1,567 shared quotes stayed byte-identical to v3 —
    sentence-granular quoting is the J drag (v4 J 0.533 vs v2's 0.648);
    the 51 TP->FN losses are 19 partial multi-span rows (parts dropped),
    29 wrong spans, 3 refusals; the 119 J-down rows kept GT inside LONGER
    quotes."""
    from src.prompts import (
        CONTRACTEVAL_PROMPT_V0,
        CONTRACTEVAL_PROMPT_V1,
        CONTRACTEVAL_PROMPT_V2,
        CONTRACTEVAL_PROMPT_V3,
        CONTRACTEVAL_PROMPT_V4,
        CONTRACTEVAL_PROMPT_V5,
        CONTRACTEVAL_SYSTEM_PROMPT,
    )

    assert "contracteval_v5" in PROMPT_VERSIONS
    assert PROMPT_VERSIONS["contracteval_v5"] is CONTRACTEVAL_PROMPT_V5
    # Byte-identical derivation chain: v0 -> v1 -> v2 -> v3 -> v4 -> v5.
    assert CONTRACTEVAL_PROMPT_V0 == CONTRACTEVAL_SYSTEM_PROMPT
    assert CONTRACTEVAL_PROMPT_V1.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V2.startswith(CONTRACTEVAL_PROMPT_V1)
    assert CONTRACTEVAL_PROMPT_V3.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V4.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V5.startswith(CONTRACTEVAL_PROMPT_V0)
    assert CONTRACTEVAL_PROMPT_V5 != CONTRACTEVAL_PROMPT_V4
    # The synthesis: verbatim fidelity AND fragment permission, both present.
    assert "Quote the exact text of that span, character for character" in CONTRACTEVAL_PROMPT_V5
    assert "never clean, normalize, or re-type the text" in CONTRACTEVAL_PROMPT_V5
    assert "any contiguous run of the original text" in CONTRACTEVAL_PROMPT_V5
    assert "sub-sentence fragment" in CONTRACTEVAL_PROMPT_V5
    assert "contains every word of the complete answer" in CONTRACTEVAL_PROMPT_V5
    assert "when the complete answer has several parts, include every part" in CONTRACTEVAL_PROMPT_V5
    assert "no more text than the answer needs" in CONTRACTEVAL_PROMPT_V5
    # Sentence-granularity tail ABSENT (the J drag / part-dropping driver).
    for forbidden in ("never a fragment of a sentence",
                      "otherwise quote the complete sentence(s)",
                      "quote the whole sentence", "when in doubt"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V5
    # Trigger + no-related contract unchanged; element-alone exception kept.
    assert "relates to the Question's subject and responds to it" in CONTRACTEVAL_PROMPT_V5
    assert "that is itself the complete answer may be quoted alone" in CONTRACTEVAL_PROMPT_V5
    assert CONTRACTEVAL_PROMPT_V5.count('"No related clause."') == 2
    # Refusal vocabulary still absent; mirror-faithful plain prompt.
    for forbidden in ("states the answer", "related but different"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V5
    assert CONTRACTEVAL_PROMPT_V5.startswith(
        "You are an assistant with strong legal knowledge")
    for forbidden in ("JSON", "json", "reasoning", "output format", "You are an AI"):
        assert forbidden not in CONTRACTEVAL_PROMPT_V5


def test_contracteval_user_template_formats():
    """The ContractEval prompt template reproduces the paper's exact user
    message shape (Context block + Question block)."""
    from src.prompts import CONTRACTEVAL_USER_TEMPLATE

    msg = CONTRACTEVAL_USER_TEMPLATE.format(
        context="FULL CONTRACT TEXT", question="Document Name question")
    assert "FULL CONTRACT TEXT" in msg
    assert "Document Name question" in msg
    assert msg.index("Context:") < msg.index("Question:")
    assert "```" in msg

