"""SorterAgent — Legal Document Classification Agent (LangChain).

Classifies documents into one of the 6 mailroom document types with confidence
scoring. The system prompt is loaded BY VERSION from ``src.prompts`` so the
evaluation loops can test exactly one prompt version per Braintrust experiment.
"""

from __future__ import annotations

import re

import structlog
from agents.base_agent import BaseAgent, build_structured_schema
from src.prompts import get_prompt

logger = structlog.get_logger(__name__)

DOC_CLASSES = [
    {"key": "contract", "label": "Contract / Agreement", "description": "Formal agreements between parties: M&A, vendor, employment, NDAs, etc."},
    {"key": "corporate_record", "label": "Corporate Record", "description": "Bylaws, resolutions, board minutes, cap table entries, incorporation docs"},
    {"key": "due_diligence", "label": "Due Diligence", "description": "Checklists, disclosure schedules, diligence memos, risk assessments"},
    {"key": "correspondence", "label": "Correspondence", "description": "Letters, emails, memos, notices between parties or with regulators"},
    {"key": "compliance_filing", "label": "Compliance Filing", "description": "SEC filings, state registrations, regulatory submissions, annual reports"},
    {"key": "court_opinion", "label": "Court Opinion", "description": "Judicial opinions and orders: published decisions, memorandum opinions, rulings"},
]

DOC_CLASS_KEYS = [d["key"] for d in DOC_CLASSES]

# ---------------------------------------------------------------------------
# Extended primary classification for the hierarchical doc-class task
# (KANBAN-033): the shared 6-class surface above stays the sorter's default;
# the doc-class eval task opts into the EXTENDED primary list via
# ``SorterAgent(doc_classes=DOCCLASS_CLASSES, schema=DOCCLASS_SCHEMA)`` so the
# existing subtype/classification surfaces (and their prompt-option == schema
# enum tests) are untouched. merger_agreement is the MAUD corpus class.
# ---------------------------------------------------------------------------
MERGER_AGREEMENT_CLASS = {
    "key": "merger_agreement",
    "label": "Merger / Acquisition Agreement",
    "description": "Merger and acquisition agreements: agreements and plans of "
                   "merger, share/asset purchase agreements (MAUD corpus)",
}
# Insurance claim documentation (docclass-merged v5+ / docclass-pilot GT):
# FNOL forms, adjuster reports/estimates, demand packages, coverage
# determinations, reservation-of-rights and denial letters, EOB statements.
INSURANCE_CLAIM_CLASS = {
    "key": "insurance_claim",
    "label": "Insurance Claim",
    "description": "Insurance claim documentation: FNOL forms, adjuster reports "
                   "and estimates, demand packages, coverage determinations, "
                   "reservation-of-rights and denial letters, EOB statements",
}
DOCCLASS_CLASSES = DOC_CLASSES + [MERGER_AGREEMENT_CLASS, INSURANCE_CLAIM_CLASS]
DOCCLASS_CLASS_KEYS = [d["key"] for d in DOCCLASS_CLASSES]

# Pilot class universe (KANBAN-090 lineage, docclass-merged/docclass-pilot GT):
# the 5 primary classes the ground truth actually contains. The three shared
# classes absent from every GT row (due_diligence, compliance_filing,
# court_opinion) stay available on the extended surface but are excluded here
# so the option list matches the data exactly.
PILOT_CLASS_KEYS = ["contract", "corporate_record", "correspondence",
                    "insurance_claim", "merger_agreement"]
DOCCLASS_PILOT_CLASSES = [c for c in DOCCLASS_CLASSES if c["key"] in PILOT_CLASS_KEYS]
DOCCLASS_PILOT_CLASS_KEYS = [d["key"] for d in DOCCLASS_PILOT_CLASSES]

# Second-level dimension for non-contract doc classes (data-necessitated
# granularity): consideration type for merger agreements (MAUD expert GT),
# record type for corporate records (content-detected from the document).
# The tertiary level is deliberately absent — MAUD category distributions and
# EDGAR exhibit codes are dataset metadata, not classification dimensions.
MERGER_SUBCLASSES = [
    {"key": "all_cash", "label": "All Cash Consideration",
     "description": "Consideration payable entirely in cash"},
    {"key": "all_stock", "label": "All Stock Consideration",
     "description": "Consideration payable entirely in stock/equity"},
    {"key": "mixed_cash_stock", "label": "Mixed Cash/Stock Consideration",
     "description": "Consideration payable in a mix of cash and stock"},
    {"key": "mixed_cash_stock_election", "label": "Mixed Cash/Stock Consideration with Election",
     "description": "Mixed consideration with a per-shareholder election"},
]
CORPORATE_RECORD_SUBCLASSES = [
    {"key": "bylaws", "label": "Bylaws",
     "description": "Corporate bylaws (EX-3.2/3.3 conventions)"},
    {"key": "articles_of_incorporation", "label": "Articles / Certificate of Incorporation",
     "description": "Charter, incl. amended and restated certificates (EX-3.1/3.2)"},
    {"key": "certificate_of_formation", "label": "Certificate of Formation",
     "description": "LLC formation certificate (EX-3.1)"},
    {"key": "charter_amendment", "label": "Charter Amendment",
     "description": "Certificate of amendment to the charter"},
    {"key": "powers_of_attorney", "label": "Power(s) of Attorney",
     "description": "Board/officer powers of attorney (EX-24.x)"},
    {"key": "subsidiary_list", "label": "Subsidiary List",
     "description": "List of subsidiaries of the registrant (EX-21.x)"},
    {"key": "rights_instrument", "label": "Rights Instrument",
     "description": "Instruments defining rights of securityholders (EX-4.x)"},
    {"key": "indenture", "label": "Indenture",
     "description": "Debt indentures and supplemental indentures (EX-25.x)"},
    {"key": "board_resolution", "label": "Board Resolution / Written Consent",
     "description": "Board resolutions, written consents, unanimous consents"},
    {"key": "officer_certificate", "label": "Officer Certificate",
     "description": "Officer's certificates (e.g. of incumbency)"},
]
DOC_SUBCLASS_UNKNOWN = "other"
CORRESPONDENCE_SUBCLASSES = [
    {"key": "demand", "label": "Demand Letter",
     "description": "Payment/performance demand from a party (non-attorney)"},
    {"key": "attorney_demand", "label": "Attorney Demand Letter",
     "description": "Demand letter issued by counsel on a law-firm letterhead"},
    {"key": "meeting_request", "label": "Meeting Request",
     "description": "Request to schedule/convene a meeting or call"},
    {"key": "press_release", "label": "Press Release",
     "description": "Public announcement distributed to media"},
    {"key": "memo", "label": "Memorandum",
     "description": "Internal memorandum (TO/FROM/RE or memo header)"},
    {"key": "email", "label": "Email",
     "description": "Email message thread (From:/To:/Subject: headers)"},
    {"key": "letter", "label": "General Letter",
     "description": "General business/legal correspondence letter"},
    {"key": "notice", "label": "Notice",
     "description": "Formal notice: annual-meeting notices, regulatory notices, "
                    "default/termination notices when not demanding payment"},
]
INSURANCE_CLAIM_SUBCLASSES = [
    {"key": "carrier", "label": "Carrier Document",
     "description": "Insurer/carrier-issued claim document (coverage "
                    "determination, denial, reservation of rights, adjuster "
                    "report issued by the carrier)"},
    {"key": "pde", "label": "Prescription Drug Event (PDE) Record",
     "description": "Pharmacy/prescription drug event claim record"},
    {"key": "outpatient", "label": "Outpatient Claim",
     "description": "Outpatient medical claim/EOB documentation"},
    {"key": "inpatient", "label": "Inpatient Claim",
     "description": "Inpatient medical claim/EOB documentation"},
]
DOC_SUBCLASSES = (MERGER_SUBCLASSES + CORPORATE_RECORD_SUBCLASSES
                  + CORRESPONDENCE_SUBCLASSES + INSURANCE_CLAIM_SUBCLASSES + [
    {"key": DOC_SUBCLASS_UNKNOWN, "label": "Other", "description": "No matching subclass"}
])
DOC_SUBCLASS_KEYS = [s["key"] for s in DOC_SUBCLASSES]

# Subclass dimension per doc class: which subclass enum applies to which
# primary class (contract keeps its own contract_subtype dimension).
SUBCLASS_DIMENSIONS: dict[str, list[dict]] = {
    "merger_agreement": MERGER_SUBCLASSES,
    "corporate_record": CORPORATE_RECORD_SUBCLASSES,
    "correspondence": CORRESPONDENCE_SUBCLASSES,
    "insurance_claim": INSURANCE_CLAIM_SUBCLASSES,
}

# Common phrasings that do not normalize to their key (singular/plural,
# spacing) — mirror of the subtype alias table above.
_DOC_SUBCLASS_ALIASES = {
    "powerofattorney": "powers_of_attorney",
    "powerattorney": "powers_of_attorney",
}


def normalize_doc_subclass(value, doc_type: str | None = None) -> str:
    """Coerce a raw sorter subclass output to a canonical doc_subclass key.

    ``doc_type`` scopes the allowed enum (merger_agreement -> consideration
    types; corporate_record -> record types); unknown values and subclasses
    from the wrong dimension become ``other``.
    """
    if value is None:
        return DOC_SUBCLASS_UNKNOWN
    raw = str(value).strip()
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if not key:
        return DOC_SUBCLASS_UNKNOWN
    if doc_type in SUBCLASS_DIMENSIONS:
        allowed = [s["key"] for s in SUBCLASS_DIMENSIONS[doc_type]]
        if raw in allowed:
            return raw
        for candidate in allowed:
            if key == re.sub(r"[^a-z0-9]", "", candidate.lower()):
                return candidate
        if key in _DOC_SUBCLASS_ALIASES and _DOC_SUBCLASS_ALIASES[key] in allowed:
            return _DOC_SUBCLASS_ALIASES[key]
        return DOC_SUBCLASS_UNKNOWN
    if raw in DOC_SUBCLASS_KEYS:
        return raw
    for candidate in DOC_SUBCLASS_KEYS:
        if key == re.sub(r"[^a-z0-9]", "", candidate.lower()):
            return candidate
    if key in _DOC_SUBCLASS_ALIASES:
        return _DOC_SUBCLASS_ALIASES[key]
    for subclass in DOC_SUBCLASSES:
        norm_label = re.sub(r"[^a-z0-9]", "", subclass["label"].lower())
        if key == norm_label or key.startswith(norm_label[:8]):
            return subclass["key"]
    return DOC_SUBCLASS_UNKNOWN

# The CONTRACT SUBGROUP dimension (CUAD corpus, 25 contract types): the
# finer-grained family of agreement a contract belongs to. The sorter outputs
# ``contract_subtype`` alongside ``doc_type`` so the mailroom knows which
# specialist expectations apply (per the CUAD dataset card, the group a
# document belongs to decides what fields to expect). Keys are normalized
# folder names from the CUAD tree; "other" is the fallback for contracts that
# fit none of the listed families.
CONTRACT_SUBTYPES = [
    {"key": "affiliate", "label": "Affiliate Agreement", "description": "Affiliate/referral program agreements"},
    {"key": "agency", "label": "Agency Agreement", "description": "Agency representation agreements"},
    {"key": "collaboration", "label": "Collaboration / Cooperation Agreement", "description": "R&D and cooperation collaborations"},
    {"key": "co_branding", "label": "Co-Branding Agreement", "description": "Co-branded marketing/product agreements"},
    {"key": "consulting", "label": "Consulting Agreement", "description": "Consulting and advisory services"},
    {"key": "development", "label": "Development Agreement", "description": "Product/software/services development"},
    {"key": "distributor", "label": "Distributor Agreement", "description": "Distribution and resale rights"},
    {"key": "endorsement", "label": "Endorsement Agreement", "description": "Endorsements and endorsement riders: celebrity/influencer deals, product or service endorsements, and endorsement riders or amendments attached to insurance, annuity, or other agreements"},
    {"key": "franchise", "label": "Franchise Agreement", "description": "Franchise rights and operations"},
    {"key": "hosting", "label": "Hosting Agreement", "description": "Web/application hosting services"},
    {"key": "ip", "label": "IP Agreement", "description": "Intellectual property transfer/license agreements"},
    {"key": "joint_venture", "label": "Joint Venture Agreement", "description": "Joint venture and project collaborations"},
    {"key": "license", "label": "License Agreement", "description": "Licensing of technology, content, or IP"},
    {"key": "maintenance", "label": "Maintenance Agreement", "description": "Maintenance and support services"},
    {"key": "manufacturing", "label": "Manufacturing Agreement", "description": "Manufacturing and supply of goods"},
    {"key": "marketing", "label": "Marketing Agreement", "description": "Marketing and promotion services"},
    {"key": "non_compete_no_solicit", "label": "Non-Compete / No-Solicit / Non-Disparagement Agreement", "description": "Restrictive-covenant agreements"},
    {"key": "outsourcing", "label": "Outsourcing Agreement", "description": "Business-process outsourcing"},
    {"key": "promotion", "label": "Promotion Agreement", "description": "Promotional services and campaigns"},
    {"key": "reseller", "label": "Reseller Agreement", "description": "Reseller and value-added distribution"},
    {"key": "service", "label": "Service Agreement", "description": "General professional/support services"},
    {"key": "sponsorship", "label": "Sponsorship Agreement", "description": "Sponsorship of events/content"},
    {"key": "strategic_alliance", "label": "Strategic Alliance Agreement", "description": "Strategic alliances and partnerships"},
    {"key": "supply", "label": "Supply Agreement", "description": "Supply of goods or materials"},
    {"key": "transportation", "label": "Transportation Agreement", "description": "Transportation and logistics services"},
]

CONTRACT_SUBTYPE_KEYS = [s["key"] for s in CONTRACT_SUBTYPES]

# Scoring constants + helpers come from the llm-dojo-scoring package (the
# single source shared with llm-mailroom; values verified identical to the
# definitions they replace, llm-dojo-scoring v0.1.0). CONTRACT_SUBTYPES stays
# local: its per-family descriptions differ from the package's and the schema
# enum (SORTER_SCHEMA) must stay byte-identical.
from llm_dojo_scoring.config import (  # noqa: E402
    DOC_SUBCLASS_EQUIVALENCES,
    SUBTYPE_ALIASES,
    SUBTYPE_EQUIVALENCES,
    SUBTYPE_UNKNOWN,
)
from llm_dojo_scoring.equivalences import equivalent_subtypes, normalize_subtype  # noqa: E402

# Private-name alias kept for test_subtype_handoff (folder -> key mapping).
_SUBTYPE_ALIASES = SUBTYPE_ALIASES


# ---------------------------------------------------------------------------
# Docclass (hierarchical) subclass equivalences — the doc_subclass mirror of
# SUBTYPE_EQUIVALENCES. Defensible family-level reads for the second-level
# dimension (KANBAN-033):
#   - mixed_cash_stock <-> mixed_cash_stock_election (an election structure IS
#     a mixed cash+stock deal with a per-shareholder choice; MAUD's categories
#     split them, but the family-level read is the same mixed structure —
#     mirrors the reseller<->distributor defensibility)
# Record types (bylaws, articles_of_incorporation, ...) have no cross-type
# families — a bylaws read is never equivalent to a charter read.
# ---------------------------------------------------------------------------
# DOC_SUBCLASS_EQUIVALENCES comes from llm_dojo_scoring.config (above).


def equivalent_doc_subclasses(a: str | None, b: str | None,
                              doc_type: str | None = None) -> bool:
    """Return True when two doc_subclass keys are the same family or members
    of the same interchangeable family class (see
    ``DOC_SUBCLASS_EQUIVALENCES``), scoped to the doc_type's own dimension
    (a consideration key is never equivalent to a record-type key)."""
    if a == b:
        return True
    if a is None or b is None:
        return False
    if doc_type in SUBCLASS_DIMENSIONS:
        allowed = {s["key"] for s in SUBCLASS_DIMENSIONS[doc_type]}
        if a not in allowed or b not in allowed:
            return False
    return any(str(a) in cls and str(b) in cls for cls in DOC_SUBCLASS_EQUIVALENCES)

# normalize_subtype / equivalent_subtypes come from llm_dojo_scoring
# (identical algorithms; the package settings are wired from the repo
# taxonomy by src/dojo_config.py).

SORTER_SCHEMA = build_structured_schema(
    {
        "doc_type": {"type": "string", "enum": DOC_CLASS_KEYS},
        "contract_subtype": {
            "type": ["string", "null"],
            "enum": CONTRACT_SUBTYPE_KEYS + [SUBTYPE_UNKNOWN],
            "description": "The contract family/subgroup — REQUIRED when doc_type is "
                           "contract, null otherwise. See the subtype list in the prompt.",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    title="ClassificationOutput",
)

# Extended schema for the hierarchical doc-class task (KANBAN-033): the same
# contract plus the 7-class primary enum and a second-level ``doc_subclass``
# dimension (consideration type / record type). ``contract_subtype`` stays the
# contract-only dimension; ``doc_subclass`` covers the non-contract classes.
# The tertiary level is absent by design (see DOCCLASS_CLASSES banner).
DOCCLASS_SCHEMA = build_structured_schema(
    {
        "doc_type": {"type": "string", "enum": DOCCLASS_CLASS_KEYS},
        "contract_subtype": {
            "type": ["string", "null"],
            "enum": CONTRACT_SUBTYPE_KEYS + [SUBTYPE_UNKNOWN],
            "description": "The contract family/subgroup — REQUIRED when doc_type is "
                           "contract, null otherwise. See the subtype list in the prompt.",
        },
        "doc_subclass": {
            "type": ["string", "null"],
            "enum": DOC_SUBCLASS_KEYS,
            "description": "The second-level class: consideration type when doc_type is "
                           "merger_agreement, record type when doc_type is corporate_record, "
                           "correspondence type when doc_type is correspondence (demand, "
                           "attorney_demand, meeting_request, press_release, memo, email, "
                           "letter, notice), claim-document type when doc_type is "
                           "insurance_claim (carrier, pde, outpatient, inpatient), "
                           "null otherwise. See the subclass list in the prompt.",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    title="DocClassClassificationOutput",
)

# Pilot schema: same shape over the 5-class pilot universe (the classes the
# docclass-merged / docclass-pilot ground truth actually contains).
DOCCLASS_PILOT_SCHEMA = build_structured_schema(
    {
        "doc_type": {"type": "string", "enum": DOCCLASS_PILOT_CLASS_KEYS},
        "contract_subtype": {
            "type": ["string", "null"],
            "enum": CONTRACT_SUBTYPE_KEYS + [SUBTYPE_UNKNOWN],
            "description": "The contract family/subgroup — REQUIRED when doc_type is "
                           "contract, null otherwise. See the subtype list in the prompt.",
        },
        "doc_subclass": {
            "type": ["string", "null"],
            "enum": DOC_SUBCLASS_KEYS,
            "description": DOCCLASS_SCHEMA["properties"]["doc_subclass"]["description"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    title="DocClassPilotClassificationOutput",
)

# Correspondence-only eval schema (KANBAN-103): the docclass contract plus
# sentiment polarity. Used ONLY by the Enron correspondence runner so the
# CUAD/MAUD/S-1 docclass evals keep their existing output shape.
SENTIMENT_LABELS = ("negative", "neutral", "positive")
SENTIMENT_SCORE_BAND = 0.25  # |pred - gt| within this band counts as a hit
SENTIMENT_LABEL_THRESHOLDS = (-0.15, 0.15)  # score → label agreement band


def normalize_sentiment_label(value) -> str | None:
    """Coerce a raw sentiment label to negative/neutral/positive, or None."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    return raw if raw in SENTIMENT_LABELS else None


def normalize_sentiment_score(value) -> float | None:
    """Parse and clamp a sentiment score to [-1.0, 1.0], or None."""
    if value is None or value == "":
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return max(-1.0, min(1.0, score))


def sentiment_label_from_score(score: float | None) -> str | None:
    """Derive a sentiment label from a clamped score (lexicon-style cutoffs)."""
    if score is None:
        return None
    lo, hi = SENTIMENT_LABEL_THRESHOLDS
    if score < lo:
        return "negative"
    if score > hi:
        return "positive"
    return "neutral"


CORRESPONDENCE_EVAL_SCHEMA = build_structured_schema(
    {
        **DOCCLASS_SCHEMA["properties"],
        "sentiment_score": {
            "type": "number",
            "minimum": -1.0,
            "maximum": 1.0,
            "description": "Polarity of the correspondence content in [-1.0, 1.0] "
                           "(negative = complaint/anger/threat/bad news; 0 = factual/"
                           "routine; positive = thanks/approval/good news).",
        },
        "sentiment_label": {
            "type": "string",
            "enum": list(SENTIMENT_LABELS),
            "description": "Polarity bucket: negative, neutral, or positive. Must "
                           "agree with sentiment_score (score < -0.15 → negative; "
                           "score > 0.15 → positive; otherwise neutral).",
        },
    },
    title="CorrespondenceClassificationOutput",
)


class SorterAgent(BaseAgent):
    """Classifies legal documents into mailroom document types.

    Two classification paths share the same output contract
    (``{"doc_type", "confidence", "reasoning"}``):

    - ``classify_json`` / ``classify`` — text documents (full extracted
      markdown text; truncation only past the hard safety cap).
    - ``classify_image`` — document page images (RVL-CDIP-style vision
      pipeline) using the versioned vision prompt (``sorter_vision_v0``).
    """

    agent_name = "sorter"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        prompt_version: str = "sorter",
        callbacks: list | None = None,
        doc_classes: list[dict] | None = None,
        schema: dict | None = None,
    ):
        super().__init__(model=model, api_key=api_key, callbacks=callbacks)
        self.prompt_version = prompt_version
        # Hierarchical doc-class task opt-in (KANBAN-033): pass the extended
        # 7-class list + DOCCLASS_SCHEMA to classify into the expanded primary
        # dimension with the doc_subclass second level. Defaults preserve the
        # shared 6-class surface byte-for-byte.
        self.doc_classes = doc_classes if doc_classes is not None else DOC_CLASSES
        self.schema = schema if schema is not None else SORTER_SCHEMA
        # The sorter classifies 25 near-synonymous contract families where
        # title-vs-operatives conflicts are common (reseller/distributor,
        # license/maintenance, development/license, ...). Medium reasoning
        # effort makes it weigh the operative clauses before committing;
        # overridden per-run via the eval runners' --reasoning-effort flag.
        self._reasoning_effort = "medium"

    def system_prompt(self) -> str:
        base_prompt = get_prompt(self.prompt_version)
        if "{{doc_type_descriptions}}" not in base_prompt:
            return base_prompt
        doc_type_descriptions = "\n".join(
            f"- {d['key']}: {d['label']} — {d['description']}"
            for d in self.doc_classes
        )
        base_prompt = base_prompt.replace("{{doc_type_descriptions}}", doc_type_descriptions)
        if "{{contract_subtypes}}" not in base_prompt:
            return base_prompt
        contract_subtypes = "\n".join(
            f"- {s['key']}: {s['label']} — {s['description']}"
            for s in CONTRACT_SUBTYPES
        )
        return base_prompt.replace("{{contract_subtypes}}", contract_subtypes)

    def classify(self, doc_text: str) -> tuple[str, float, str]:
        """Classify a document and return (doc_type, confidence, reasoning).

        Args:
            doc_text: The full text content of the document.

        Returns:
            Tuple of (doc_type key, confidence 0-1, reasoning string).
        """
        truncated = self.truncate_input(doc_text)
        result = self._call_structured(
            f"Classify this legal document:\n\n{truncated}",
            json_schema=SORTER_SCHEMA,
            temperature=0.1,
        )

        if result.get("_parse_error"):
            logger.error("sorter_parse_error")
            return ("correspondence", SUBTYPE_UNKNOWN, 0.3, "parse error — defaulting to correspondence")

        doc_type = result.get("doc_type", "correspondence")
        if doc_type not in DOC_CLASS_KEYS:
            doc_type = "correspondence"
        contract_subtype = normalize_subtype(
            result.get("contract_subtype") if doc_type == "contract" else None
        )
        try:
            confidence = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        reasoning = result.get("reasoning", "")

        logger.info("classified", doc_type=doc_type, contract_subtype=contract_subtype,
                    confidence=confidence)
        return (doc_type, contract_subtype, confidence, reasoning)

    def classify_json(self, doc_text: str, subtype_focus: bool = False,
                      correspondence_focus: bool = False) -> dict:
        """Classify and return the raw structured dict (used by eval loops).

        With ``subtype_focus=True`` the model is explicitly TASKED with
        sorting the document into its contract subtype: the user message tells
        it the document IS a contract and that the subtype assignment is the
        decision being scored — used by the chained eval, whose rows are all
        contracts, so the sorter scores represent the subtype task rather
        than a general doc-type gate.

        With ``correspondence_focus=True`` the model is tasked with the
        correspondence-only surface (KANBAN-103): ``doc_type`` is
        correspondence, ``doc_subclass`` is the communication function, and
        ``sentiment_score`` / ``sentiment_label`` score content polarity.
        """
        truncated = self.truncate_input(doc_text)
        if subtype_focus:
            user_message = (
                "This document IS a contract (all documents in this task are "
                "contracts). Your job is to sort it into its correct CONTRACT "
                "SUBTYPE: assign the contract_subtype key that best matches its "
                "agreement family, and confirm doc_type as \"contract\".\n\n"
                f"Contract text:\n\n{truncated}"
            )
        elif correspondence_focus:
            user_message = (
                "This document IS correspondence (all documents in this task "
                "are correspondence). Assign doc_type as \"correspondence\", "
                "the communication-function doc_subclass (demand, "
                "attorney_demand, meeting_request, press_release, memo, email, "
                "letter, or notice — classify by what the communication DOES, "
                "not its delivery format), and a sentiment_score / "
                "sentiment_label for the content.\n\n"
                f"Correspondence text:\n\n{truncated}"
            )
        else:
            user_message = f"Classify this legal document:\n\n{truncated}"
        result = self._call_structured(
            user_message,
            json_schema=self.schema,
            temperature=0.1,
        )
        if result.get("_parse_error"):
            return {"doc_type": "correspondence", "contract_subtype": None,
                    "confidence": 0.3, "reasoning": "parse error"}
        valid_keys = [d["key"] for d in self.doc_classes]
        doc_type = result.get("doc_type", "correspondence")
        if doc_type not in valid_keys:
            doc_type = "correspondence"
        result["doc_type"] = doc_type
        result["contract_subtype"] = normalize_subtype(
            result.get("contract_subtype") if doc_type == "contract" else None
        )
        props = self.schema.get("properties") or {}
        if "doc_subclass" in props:
            result["doc_subclass"] = normalize_doc_subclass(
                result.get("doc_subclass") if doc_type in SUBCLASS_DIMENSIONS else None,
                doc_type,
            )
        if "sentiment_label" in props or "sentiment_score" in props:
            score = normalize_sentiment_score(result.get("sentiment_score"))
            label = normalize_sentiment_label(result.get("sentiment_label"))
            if label is None:
                label = sentiment_label_from_score(score)
            result["sentiment_score"] = score
            result["sentiment_label"] = label
        return result

    # ------------------------------------------------------------------
    # Vision path (RVL-CDIP-style image classification)
    # ------------------------------------------------------------------

    def _docclass_keys(self) -> list[str]:
        """The doc_type keys of the agent's (possibly extended) class list."""
        return [d["key"] for d in self.doc_classes]

    def _parse_vision_output(self, raw: str, valid_keys: list[str]) -> dict:
        """Parse the tag-based vision output into the standard contract.

        Handles the docclass vision prompt's extended tags (``<label>``,
        ``<subclass>``, ``<confidence>``, ``<reasoning>``) and the
        UNREADABLE sentinel: when the model reports the page images are
        blank/corrupted/truncated (``<label>UNREADABLE</label>``), or the
        label fails to parse, ``unreadable``/``invalid_label`` are set so the
        caller (the vision-primary eval path) can fall back to the text pass.

        Returns ``{"doc_type", "contract_subtype", "doc_subclass",
        "confidence", "reasoning", "unreadable", "invalid_label"}``.
        """
        import re

        from src.classifier import (
            clean_prediction,
            extract_confidence,
            extract_reasoning,
        )

        if not raw or not raw.strip():
            return {"doc_type": None, "contract_subtype": None, "doc_subclass": None,
                    "confidence": 0.0, "reasoning": "", "unreadable": True,
                    "invalid_label": False}

        label_match = re.search(
            r"<label>\s*([^<]+?)\s*</label>", raw, flags=re.IGNORECASE | re.DOTALL
        )
        tag_label = label_match.group(1).strip().lower() if label_match else ""
        if tag_label == "unreadable":
            return {"doc_type": None, "contract_subtype": None, "doc_subclass": None,
                    "confidence": 0.0, "reasoning": extract_reasoning(raw) or "",
                    "unreadable": True, "invalid_label": False}

        # The tag label validates against the (possibly extended) class list;
        # ``clean_prediction`` only knows the shared 6 classes, so it is the
        # fallback for tag-less legacy outputs only.
        if tag_label and tag_label in valid_keys:
            doc_type = tag_label
        else:
            doc_type = clean_prediction(raw)
        if doc_type not in valid_keys:
            logger.error("sorter_vision_invalid_label", raw_label=doc_type)
            return {"doc_type": None, "contract_subtype": None, "doc_subclass": None,
                    "confidence": extract_confidence(raw) or 0.0,
                    "reasoning": extract_reasoning(raw) or "", "unreadable": False,
                    "invalid_label": True}

        has_subclass = "doc_subclass" in (self.schema.get("properties") or {})
        raw_subclass = None
        if has_subclass and doc_type in SUBCLASS_DIMENSIONS:
            subclass_match = re.search(
                r"<subclass>\s*([^<]+?)\s*</subclass>", raw,
                flags=re.IGNORECASE | re.DOTALL,
            )
            subclass_text = subclass_match.group(1).strip() if subclass_match else ""
            if subclass_text.lower() not in ("null", "none", ""):
                raw_subclass = normalize_doc_subclass(subclass_text, doc_type)

        confidence = extract_confidence(raw)
        if confidence is None:
            confidence = 0.5
        reasoning = extract_reasoning(raw)
        return {"doc_type": doc_type, "contract_subtype": None,
                "doc_subclass": raw_subclass, "confidence": confidence,
                "reasoning": reasoning, "unreadable": False,
                "invalid_label": False}

    def classify_image(self, image_base64: str, image_format: str = "png") -> dict:
        """Classify a document PAGE IMAGE with a vision model (qwen).

        Uses the versioned vision prompt (``sorter_vision_v0`` / the docclass
        vision prompt): the intro (checks + scratchpad procedure) goes in the
        system message, the output contract + worked examples go in the
        image-bearing user message — the same split RVL-CDIP applies
        (``## Output format`` marker).

        Returns the same contract as ``classify_json`` plus the
        vision-path flags: ``{"doc_type", "contract_subtype", "doc_subclass",
        "confidence", "reasoning", "unreadable", "invalid_label"}``. The
        six-class keys are kept byte-compatible: the default 6-class sorter
        (no extended ``doc_classes``/``schema``) returns no ``doc_subclass``
        and falls back to ``correspondence`` for invalid labels exactly as
        before; the extended docclass sorter additionally normalizes
        ``doc_subclass`` per the class dimension.
        """
        from src.openrouter_utils import split_prompt

        valid_keys = self._docclass_keys()
        prompt_text = get_prompt(self.prompt_version)
        system_text, user_text = split_prompt(prompt_text)
        if not system_text:
            system_text, user_text = prompt_text, "Classify the document in this image."

        raw = self._call_vision(
            system_prompt=system_text,
            user_text=user_text,
            image_base64=image_base64,
            image_format=image_format,
            temperature=0.1,
            max_tokens=self._max_tokens,
        )

        result = self._parse_vision_output(raw, valid_keys)
        if result["doc_type"] is None and not result["unreadable"]:
            result["doc_type"] = "correspondence"
        if "doc_subclass" not in (self.schema.get("properties") or {}):
            # Strict legacy contract (6-class surface): the shared vision
            # consumers read exactly {doc_type, confidence, reasoning}.
            return {"doc_type": result["doc_type"],
                    "confidence": result["confidence"],
                    "reasoning": result["reasoning"]}
        logger.info("classified_vision", doc_type=result["doc_type"],
                    confidence=result["confidence"])
        return result

    def classify_document(self, pages_base64: list[str], image_format: str = "png") -> dict:
        """Classify a FULL PDF document in ONE vision call.

        Every rendered page of the PDF is sent to the model in a single request
        (``_call_vision_multi``) — one classification per document, so the
        model reads the entire agreement (recitals, sections, exhibits,
        signature pages) before deciding. Returns the standard contract:
        ``{"doc_type", "confidence", "reasoning"}`` (plus the docclass
        extension keys — see ``classify_image``).
        """
        from src.openrouter_utils import split_prompt

        if not pages_base64:
            return {"doc_type": "correspondence", "contract_subtype": None, "doc_subclass": None,
                    "confidence": 0.0, "reasoning": "no page images",
                    "unreadable": True, "invalid_label": False}

        valid_keys = self._docclass_keys()
        prompt_text = get_prompt(self.prompt_version)
        system_text, user_text = split_prompt(prompt_text)
        if not system_text:
            system_text, user_text = prompt_text, "Classify the document in these page images."

        raw = self._call_vision_multi(
            system_prompt=system_text,
            user_text=user_text,
            images=[(b64, image_format) for b64 in pages_base64],
            temperature=0.1,
            max_tokens=self._max_tokens,
        )

        result = self._parse_vision_output(raw, valid_keys)
        if result["doc_type"] is None and not result["unreadable"]:
            result["doc_type"] = "correspondence"
        if "doc_subclass" not in (self.schema.get("properties") or {}):
            # Strict legacy contract (6-class surface) — see classify_image.
            return {"doc_type": result["doc_type"],
                    "confidence": result["confidence"],
                    "reasoning": result["reasoning"]}
        logger.info("classified_document", doc_type=result["doc_type"],
                    pages=len(pages_base64), confidence=result["confidence"])
        return result

    def re_evaluate(self, doc_text: str, previous_result: dict) -> tuple[str, float, str]:
        """Re-evaluate a document after low-confidence classification.

        Args:
            doc_text: The full text content.
            previous_result: Dict with keys 'doc_type', 'confidence', 'reasoning'.

        Returns:
            Updated (doc_type, confidence, reasoning).
        """
        prompt = f"""RE-EVALUATION REQUESTED

Previous classification attempt produced low confidence. Please re-analyze this document more carefully.

Previous result:
- Assigned class: {previous_result.get('doc_type', 'unknown')}
- Confidence: {previous_result.get('confidence', 0)}
- Previous reasoning: {previous_result.get('reasoning', 'N/A')}

Document text:
{doc_text}

Provide your best classification with justification."""

        result = self._call_structured(prompt, json_schema=SORTER_SCHEMA, temperature=0.1)

        if result.get("_parse_error"):
            return (previous_result.get("doc_type", "correspondence"), 0.3, "re-evaluation parse error")

        doc_type = result.get("doc_type", previous_result.get("doc_type", "correspondence"))
        try:
            confidence = float(result.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        return (doc_type, confidence, result.get("reasoning", ""))
