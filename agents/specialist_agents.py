"""Specialist agents for field extraction from each document type (LangChain).

Each specialist knows how to extract fields specific to its document type and
is driven by a versioned prompt from ``src.prompts``. Schemas are exported as
module constants so the eval loops and judges can reference the same contracts.
"""

from __future__ import annotations

import structlog
from agents.base_agent import BaseAgent, build_structured_schema
from src.prompts import CONTRACTS_AUDIT_PROMPT_V0, get_prompt

logger = structlog.get_logger(__name__)


def _norm(text: str) -> str:
    """Normalize clause text for dedupe: whitespace-collapse + casefold.

    The chunk overlap window re-quotes a clause verbatim, so a
    whitespace/case-insensitive comparison makes the duplicate a no-op.
    """
    if text is None:
        return ""
    return " ".join(str(text).split()).casefold()


def _merge_reasoning(acc, chunk_reasoning) -> dict:
    """Union two per-chunk reasoning traces into one.

    Entries dedupe by field name (first-witness evidence + section reference
    win — the chunk that first located the value holds its evidence); the
    summaries join in chunk order with a marker so the merged trace covers
    every window. A missing side degrades gracefully (None-safe).
    """
    acc = acc if isinstance(acc, dict) else {}
    chunk_reasoning = chunk_reasoning if isinstance(chunk_reasoning, dict) else {}

    entries: dict[str, dict] = {}
    for entry in list(acc.get("entries") or []) + list(chunk_reasoning.get("entries") or []):
        if not isinstance(entry, dict) or not entry.get("field"):
            continue
        entries.setdefault(entry["field"], entry)

    summaries = [s for s in (acc.get("summary"), chunk_reasoning.get("summary")) if s]
    return {
        "summary": "\n\n".join(summaries) if summaries else "",
        "entries": list(entries.values()),
    }


def _nullable_string(description: str = "") -> dict:
    return {"type": ["string", "null"], "description": description}


def _string_array(description: str = "") -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def normalize_extraction(result: dict, schema: dict) -> dict:
    """Guarantee the extraction carries EVERY schema field.

    The model occasionally omits a field (e.g. ``confidence``) or returns a
    malformed shape. This fills missing keys with their schema defaults
    (null for nullable strings, [] for arrays, 0.0 for numbers) so downstream
    scoring and reporting always see a complete, conformant extraction.
    """
    normalized = dict(result or {})
    for key, spec in (schema.get("properties") or {}).items():
        if key in normalized and normalized[key] not in (None, ""):
            continue
        type_spec = spec.get("type")
        if isinstance(type_spec, list):
            type_spec = next((t for t in type_spec if t != "null"), type_spec[0])
        if type_spec == "array":
            normalized[key] = normalized.get(key) or []
        elif type_spec == "number":
            normalized[key] = normalized.get(key) if isinstance(normalized.get(key), (int, float)) else 0.0
        else:
            normalized[key] = normalized.get(key) if normalized.get(key) not in (None, "") else None
    return normalized


# =============================================================================
# Extraction schemas (single source of truth for specialists + judges)
# =============================================================================

# =============================================================================
# Audit schema (KANBAN-060 runner-level audit pass output)
# =============================================================================

AUDIT_SCHEMA = build_structured_schema({
    "missing_obligations": {
        "type": "array",
        "description": "Obligation clause sentences present in the window but "
                       "NOT already quoted by the extraction — one entry per "
                       "distinct clause sentence, quoted verbatim, tagged with "
                       "its EXACT canonical CUAD category name.",
        "items": build_structured_schema({
            "category": {"type": "string", "description": "Exact canonical CUAD "
                          "category name (one of the 32 obligation categories)."},
            "clause": {"type": "string", "description": "The complete clause "
                        "sentence, quoted VERBATIM from the window text."},
        }, required=["category", "clause"], title="MissingObligation"),
    },
}, required=["missing_obligations"], title="AuditOutput")


CONTRACTS_SCHEMA = build_structured_schema({
    "reasoning": {
        "type": "object",
        "description": "Per-field reasoning trace, produced BEFORE finalizing the "
                       "extraction: a summary of the scan plus one entry per populated "
                       "field naming the field, its evidence (short verbatim quote or "
                       "definition/alias note), and the section reference where it was "
                       "found. Describes HOW each value was found — never part of the "
                       "clause text and never replaces an extracted value.",
        "properties": {
            "summary": {"type": "string"},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "evidence": {"type": "string"},
                        "section_ref": {"type": ["string", "null"]},
                    },
                    "required": ["field", "evidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "entries"],
        "additionalProperties": False,
    },
    "document_name": _nullable_string("The name of the contract (e.g. 'Web Hosting Agreement')"),
    "parties": _string_array("The names of the contracting parties"),
    "effective_date": _nullable_string("YYYY-MM-DD (ISO)"),
    "term_length": _nullable_string("The full duration or term of the agreement, including any riders"),
    "termination_clauses": _string_array("Conditions under which the agreement can be terminated (verbatim operative language)"),
    "governing_law": _nullable_string("The jurisdiction whose laws govern the agreement (governing-law sentence only)"),
    "key_obligations": _string_array("Major obligations of each party (verbatim operative language, one item per obligation)"),
    "contract_value": _nullable_string("The monetary value or consideration"),
    "renewal_terms": _nullable_string("Renewal, extension, or rollover terms (automatic or otherwise)"),
    "confidence": {
        "type": "number", "minimum": 0.0, "maximum": 1.0,
        "description": "Evidence-grounded extraction confidence (share of fields found, "
                        "lowered by uncertain values or truncation; never a fixed default)",
    },
})

CORPORATE_RECORDS_SCHEMA = build_structured_schema({
    "entity_name": _nullable_string(),
    "record_type": _nullable_string("bylaws, resolution, minutes, cap table, etc."),
    "effective_date": _nullable_string("mm/dd/yyyy"),
    "key_provisions": _string_array(),
    "signatories": _string_array(),
    "jurisdiction": _nullable_string(),
    "filing_number": _nullable_string(),
})

DUE_DILIGENCE_SCHEMA = build_structured_schema({
    "target_entity": _nullable_string(),
    "diligence_type": _nullable_string("legal, financial, operational, tax, etc."),
    "material_findings": _string_array(),
    "risk_flags": _string_array(),
    "outstanding_items": _string_array(),
    "document_date": _nullable_string("mm/dd/yyyy"),
    "prepared_by": _nullable_string(),
})

CORRESPONDENCE_SCHEMA = build_structured_schema({
    "sender": _nullable_string(),
    "recipient": _nullable_string(),
    "additional_recipients": _string_array(),
    "communication_type": _nullable_string("letter, email, memo, notice, demand, etc."),
    "communication_date": _nullable_string("mm/dd/yyyy"),
    "key_points": _string_array(),
    "demand_amount": _nullable_string(),
    "action_items": _string_array(),
    "urgency": _nullable_string("high, medium, low, immediate, etc."),
    "referenced_communications": _string_array(),
})

COMPLIANCE_FILING_SCHEMA = build_structured_schema({
    "filing_type": _nullable_string("10-K, 10-Q, 8-K, DEF 14A, Schedule 13D, etc."),
    "regulatory_body": _nullable_string("SEC, state secretary, etc."),
    "filing_date": _nullable_string("mm/dd/yyyy"),
    "due_date": _nullable_string("mm/dd/yyyy"),
    "entity_name": _nullable_string(),
    "key_requirements": _string_array(),
    "status": _nullable_string("filed, pending, late, etc."),
    "reference_number": _nullable_string(),
})

COURT_OPINIONS_SCHEMA = build_structured_schema({
    "case_name": _nullable_string("e.g., Smith v. Jones"),
    "court": _nullable_string(),
    "date_decided": _nullable_string("mm/dd/yyyy"),
    "docket_number": _nullable_string(),
    "opinion_type": _nullable_string("majority, dissenting, concurring, per curiam, order"),
    "parties": _string_array(),
    "holding": _nullable_string(),
    "legal_issues": _string_array(),
    "outcome": _nullable_string("affirmed, reversed, remanded, dismissed, etc."),
    "citations": _string_array(),
    "authored_by": _nullable_string(),
})

INSURANCE_CLAIMS_SCHEMA = build_structured_schema({
    "claim_number": _nullable_string("Claim reference exactly as printed"),
    "policy_number": _nullable_string("Policy identifier exactly as printed"),
    "insurer": _nullable_string("Insurance company as named"),
    "insured_party": _nullable_string("Insured person/entity as named"),
    "claim_type": _nullable_string("auto | property | liability | health | life | workers_comp | other"),
    "date_of_loss": _nullable_string("As stated; never computed"),
    "date_filed": _nullable_string("As stated; never computed"),
    "claimed_amount": _nullable_string("Currency + amount exactly as stated; never converted"),
    "adjuster": _nullable_string("Only when the documents identify one"),
    "damages_description": _nullable_string("The loss/damages as described by the documents"),
    "coverage_determination": _nullable_string("approved | denied | partial | pending — only what is WRITTEN"),
    "denial_reasons": _string_array("Stated denial/limitation grounds; empty when approved"),
    "supporting_documents": _string_array("Documents the package references"),
    "confidence": {
        "type": "number", "minimum": 0.0, "maximum": 1.0,
        "description": "Evidence-grounded extraction confidence",
    },
})

SPECIALIST_SCHEMAS = {
    "contract": CONTRACTS_SCHEMA,
    "corporate_record": CORPORATE_RECORDS_SCHEMA,
    "due_diligence": DUE_DILIGENCE_SCHEMA,
    "correspondence": CORRESPONDENCE_SCHEMA,
    "compliance_filing": COMPLIANCE_FILING_SCHEMA,
    "court_opinion": COURT_OPINIONS_SCHEMA,
    "insurance_claim": INSURANCE_CLAIMS_SCHEMA,
}


def get_extraction_schema(doc_type: str) -> dict | None:
    """Return the extraction JSON schema for a doc type (None if unknown)."""
    return SPECIALIST_SCHEMAS.get(doc_type)


# =============================================================================
# Specialist agents
# =============================================================================


class _SpecialistBase(BaseAgent):
    """Shared extract() implementation over a per-class schema."""

    schema: dict
    handoff_context: str | None = None

    # ------------------------------------------------------------------
    # Chunked extraction pass (v15+ architectural layer)
    # ------------------------------------------------------------------
    # Contracts up to 335k chars exceed any single-call input budget, and
    # head+tail truncation drops the MIDDLE — exactly where obligation
    # families concentrate. Chunked mode splits the document on paragraph
    # boundaries into overlapping windows, extracts each window in its own
    # call, and merges: list fields union with normalized dedupe (overlap
    # re-quotes the same clause), scalars keep the first non-null value,
    # confidence takes the max. Nothing is truncated; the merge is the
    # completeness guarantee.
    # ------------------------------------------------------------------

    def extract_chunked(self, doc_text: str,
                        chunk_chars: int = 90_000,
                        overlap_chars: int = 8_000) -> dict:
        """Extract a long document in overlapping chunks and merge the passes.

        Documents that fit in a single window take the plain single-pass
        path (``extract``) — identical behavior to non-chunked mode, so
        chunking can never change small-document output. Longer documents
        are split, each window extracted in its own call, and merged: list
        fields union with normalized dedupe, scalars keep the first non-null
        value, confidence takes the max. A chunk that fails to parse (or
        raises) is skipped, not fatal — the surviving chunks still merge.
        """
        chunks = self._split_chunks(doc_text, chunk_chars, overlap_chars)
        self._last_n_chunks = len(chunks)
        if len(chunks) == 1:
            return self.extract(doc_text)
        merged: dict | None = None
        total_usage: dict | None = None
        failed = 0
        for index, chunk in enumerate(chunks, start=1):
            header = (f"EXTRACTION CHUNK {index} OF {len(chunks)} — this is one "
                      f"window of the agreement; extract every family occurrence "
                      f"present in THIS chunk (see the system prompt's chunk duty).\n")
            user_message = (
                f"{header}Extract fields from this {self._doc_label} document (chunk "
                f"{index} of {len(chunks)}):\n\n{chunk}"
            )
            if self.handoff_context:
                user_message = f"{self.handoff_context}\n\n{user_message}"
            try:
                result = self._call_structured(
                    user_message,
                    json_schema=self.schema,
                    temperature=0.1,
                )
            except Exception as exc:  # noqa: BLE001 - one bad chunk must not abort
                logger.warning("chunk_call_failed", agent=self.agent_name,
                               chunk=index, total=len(chunks), error=str(exc)[:200])
                failed += 1
                continue
            if self._last_usage:
                total_usage = self._sum_usage(total_usage, self._last_usage)
            if result.get("_parse_error"):
                failed += 1
                continue
            if self._confidence_missing(result):
                result["confidence"] = round(self._evidence_confidence(result), 4)
            result = normalize_extraction(result, self.schema)
            merged = result if merged is None else self._merge_extractions(merged, result)
        self._last_usage = total_usage
        self._last_truncated = False
        self._last_chunked = True
        if merged is None:
            return {"_parse_error": True}
        return merged

    @staticmethod
    def _sum_usage(acc: dict | None, usage: dict) -> dict:
        """Sum per-chunk usage dicts (prompt/completion/total tokens, cost)."""
        merged = dict(acc or {})
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            merged[key] = (merged.get(key) or 0) + int(usage.get(key) or 0)
        cost = usage.get("cost")
        if cost is not None:
            merged["cost"] = (merged.get("cost") or 0.0) + float(cost)
        return merged

    @staticmethod
    def _split_chunks(text: str, chunk_chars: int,
                      overlap_chars: int) -> list[str]:
        """Paragraph-aware chunking with a trailing overlap window.

        Paragraphs (``\\n\\n``) are kept intact; a single paragraph larger
        than the budget is hard-split on sentence-ish boundaries. Every chunk
        after the first is prepended with the previous chunk's tail so a
        clause crossing the cut is visible on both sides (the merge dedupes).
        """
        if len(text) <= chunk_chars:
            return [text]
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for para in paragraphs:
            while len(para) > chunk_chars:  # pathological single paragraph
                chunks.append(para[:chunk_chars])
                para = para[chunk_chars:]
            if current and current_len + len(para) + 2 > chunk_chars:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            current.append(para)
            current_len += len(para) + 2
        if current:
            chunks.append("\n\n".join(current))
        if len(chunks) > 1 and overlap_chars > 0:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                tail = chunks[i - 1][-overlap_chars:]
                if "\n\n" in tail:
                    tail = tail[tail.find("\n\n") + 2:]
                overlapped.append(f"{tail}\n\n{chunks[i]}")
            chunks = overlapped
        return chunks

    @staticmethod
    def _merge_extractions(acc: dict, chunk: dict) -> dict:
        """Union the per-chunk extractions into one composite output.

        List fields union with normalized dedupe (case/whitespace-insensitive,
        so the overlap window re-quoting a clause is a no-op); scalar fields
        keep the FIRST non-null value in document order; confidence takes the
        max across chunks (a clause seen in one window is real evidence).
        ``reasoning`` is a TRACE: its entries union across chunks (dedupe by
        field, the first-witness evidence + section reference wins — the chunk
        that first located the value holds the evidence) and the summaries
        join with chunk markers, so the merged trace covers the whole
        document instead of only the first window.
        """
        merged = dict(acc)
        for key, value in chunk.items():
            if key == "confidence":
                merged["confidence"] = max(
                    float(merged.get("confidence") or 0.0), float(value or 0.0))
                continue
            if key == "_parse_error":
                continue
            if key == "reasoning":
                merged["reasoning"] = _merge_reasoning(
                    merged.get("reasoning"), value)
                continue
            if isinstance(value, list):
                seen = {_norm(item) for item in merged.get(key) or []}
                for item in value:
                    if _norm(item) not in seen:
                        merged.setdefault(key, []).append(item)
                        seen.add(_norm(item))
            elif value not in (None, ""):
                # first NON-NULL value in document order wins (the accumulator
                # may hold a present-but-null key from an earlier chunk)
                if merged.get(key) in (None, ""):
                    merged[key] = value
        return merged

    def extract(self, doc_text: str) -> dict:
        self._last_chunked = False
        truncated = self.truncate_input(doc_text)
        # When the sorter hands this document off, its classification is
        # prefixed to the extraction call so the specialist extracts with the
        # expected clause set in mind (mailroom chained pipeline).
        user_message = f"Extract fields from this {self._doc_label} document:\n\n{truncated}"
        if self.handoff_context:
            user_message = (
                f"{self.handoff_context}\n\n"
                f"Extract fields from this {self._doc_label} document:\n\n{truncated}"
            )
        result = self._call_structured(
            user_message,
            json_schema=self.schema,
            temperature=0.1,
        )
        if result.get("_parse_error"):
            logger.error("specialist_parse_error", agent=self.agent_name)
            return {"_parse_error": True}
        if self._confidence_missing(result):
            # The model occasionally omits `confidence`; derive it from the
            # evidence in THIS document (the share of schema fields actually
            # found) — the rule the prompt itself states.
            result["confidence"] = round(self._evidence_confidence(result), 4)
        # Guarantee every schema field is present (null/[]/0.0 defaults).
        return normalize_extraction(result, self.schema)

    def _confidence_missing(self, result: dict) -> bool:
        value = result.get("confidence")
        return value is None or (isinstance(value, (int, float)) and value == 0.0)

    def _evidence_confidence(self, result: dict) -> float:
        """Share of schema fields actually found in the extraction (0.0-1.0).

        List fields count as found when non-empty; string fields when
        non-null. The confidence never exceeds what the extracted facts
        justify, mirroring the specialist prompts' evidence rule.
        """
        properties = (self.schema.get("properties") or {})
        total = 0
        found = 0
        for key, spec in properties.items():
            if key in ("confidence", "reasoning"):
                continue
            value = result.get(key)
            type_spec = spec.get("type")
            if isinstance(type_spec, list):
                type_spec = next((t for t in type_spec if t != "null"), type_spec[0])
            total += 1
            if type_spec == "array":
                found += 1 if value not in (None, [], "") else 0
            else:
                found += 1 if value not in (None, "") else 0
        return found / total if total else 0.0

    @property
    def _doc_label(self) -> str:
        return self.agent_name.replace("_specialist", "").replace("_", " ")


class ContractsSpecialist(_SpecialistBase):
    agent_name = "contracts_specialist"
    schema = CONTRACTS_SCHEMA

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 prompt_version: str = "contracts_specialist", callbacks: list | None = None):
        super().__init__(model=model, api_key=api_key, callbacks=callbacks)
        self.prompt_version = prompt_version
        self._last_chunked = False
        self._last_n_chunks = 0

    def system_prompt(self) -> str:
        return get_prompt(self.prompt_version)

    # ------------------------------------------------------------------
    # Audit pass (KANBAN-060): a SECOND structured call with missed-category
    # feedback. The measured mechanism behind the ~645 absent (doc, category)
    # pairs (551 of 645 labels verbatim-in-text, model emits ZERO for the
    # category) is emission-stage category-selective omission — a single
    # forward generation cannot re-read, so no prompt lever moved it. The
    # audit re-reads each extraction window, feeds back the already-quoted
    # clauses, and returns the categories' missing clause sentences (verbatim,
    # ADDING-only, never-fabricate). The merge is a union with normalized
    # dedupe — nothing is removed.
    # ------------------------------------------------------------------

    def audit_extraction(self, doc_text: str, extraction: dict,
                         chunk_chars: int = 90_000,
                         overlap_chars: int = 8_000) -> dict:
        """Run the missed-category audit pass over the extraction.

        Uses the SAME windows as ``extract_chunked`` (single-window documents
        get one whole-text audit call; longer documents one call per window).
        Returns the extraction with any missing obligation clauses merged in
        (``key_obligations`` union with normalized dedupe + canonical-tagged
        reasoning entries). A failing/parse-error audit call is skipped, never
        fatal. ``_last_usage`` holds the summed extract + audit usage.
        """
        windows = self._split_chunks(doc_text, chunk_chars, overlap_chars)
        self._last_n_chunks = max(len(windows), getattr(self, "_last_n_chunks", 0) or 0)
        audit_usage: dict | None = self._last_usage
        missing: list[tuple[str, str]] = []

        already = self._audit_already_quoted(extraction)
        audit_block = (
            f"\n\n{CONTRACTS_AUDIT_PROMPT_V0}\n\n"
            f"ALREADY-EXTRACTED OBLIGATION CLAUSES (verbatim quotes, grouped "
            f"by canonical category):\n{already}"
        )
        for index, window in enumerate(windows, start=1):
            # Prefix-cache consolidation: the audit user message replicates the
            # extraction call's EXACT layout (extract / extract_chunked) and
            # the audit call reuses the extraction's system prompt, so the
            # shared prefix (system + layout + window text) is byte-identical
            # and the re-read hits the provider's automatic context cache.
            if len(windows) == 1:
                user_message = (
                    f"Extract fields from this {self._doc_label} document:\n\n"
                    f"{window}"
                )
            else:
                header = (f"EXTRACTION CHUNK {index} OF {len(windows)} — this is "
                          f"one window of the agreement; extract every family "
                          f"occurrence present in THIS chunk (see the system "
                          f"prompt's chunk duty).\n")
                user_message = (
                    f"{header}Extract fields from this {self._doc_label} "
                    f"document (chunk {index} of {len(windows)}):\n\n{window}"
                )
            if self.handoff_context:
                user_message = f"{self.handoff_context}\n\n{user_message}"
            user_message += audit_block
            try:
                result = self._call_structured(
                    user_message,
                    json_schema=AUDIT_SCHEMA,
                    temperature=0.1,
                )
            except Exception as exc:  # noqa: BLE001 - one bad window must not abort
                logger.warning("audit_call_failed", agent=self.agent_name,
                               window=index, total=len(windows), error=str(exc)[:200])
                continue
            if self._last_usage:
                audit_usage = self._sum_usage(audit_usage, self._last_usage)
            if result.get("_parse_error"):
                continue
            for entry in (result.get("missing_obligations") or []):
                if not isinstance(entry, dict):
                    continue
                category = str(entry.get("category") or "").strip()
                clause = str(entry.get("clause") or "").strip()
                if category and clause:
                    missing.append((category, clause))

        if missing:
            extraction = self._merge_audit(extraction, missing)

        self._last_usage = audit_usage
        self._last_truncated = False
        return extraction

    @staticmethod
    def _audit_already_quoted(extraction: dict) -> str:
        """Render the extraction's quoted obligation clauses for the audit
        input, grouped by canonical category (reasoning entries are the
        canonical-tagged trace; the clause lists are the verbatim quotes)."""
        lines: list[str] = []
        reasoning = (extraction.get("reasoning") or {})
        entries = reasoning.get("entries") or [] if isinstance(reasoning, dict) else []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            field = str(entry.get("field") or "").strip()
            evidence = str(entry.get("evidence") or "").strip()
            if field and evidence and _norm(evidence) not in seen:
                seen.add(_norm(evidence))
                lines.append(f"- {field}: {evidence}")
        for field in ("key_obligations", "termination_clauses"):
            for item in extraction.get(field) or []:
                text = str(item).strip()
                if text and _norm(text) not in seen:
                    seen.add(_norm(text))
                    lines.append(f"- {field}: {text}")
        return "\n".join(lines) if lines else "(none)"

    @staticmethod
    def _merge_audit(extraction: dict, missing: list[tuple[str, str]]) -> dict:
        """Union the audit's missing clauses into the extraction.

        Clause strings append to ``key_obligations`` with normalized dedupe
        (a clause the extraction already quoted — or the audit re-quoted
        across windows — is a no-op); a canonical-tagged reasoning entry is
        added per clause so the KPI mapper routes it to its category.
        """
        merged = dict(extraction)
        merged.setdefault("key_obligations", [])
        seen = {_norm(item) for item in merged["key_obligations"]}
        entries = list(((extraction.get("reasoning") or {}).get("entries") or [])
                       if isinstance(extraction.get("reasoning"), dict) else [])
        added = 0
        for category, clause in missing:
            if _norm(clause) in seen:
                continue
            merged["key_obligations"].append(clause)
            seen.add(_norm(clause))
            entries.append({
                "field": category,
                "evidence": clause,
                "section_ref": "audit-pass",
            })
            added += 1
        if added:
            reasoning = extraction.get("reasoning") if isinstance(extraction.get("reasoning"), dict) else {}
            merged["reasoning"] = {
                "summary": reasoning.get("summary") or "",
                "entries": entries,
            }
        return merged


class CorporateRecordsSpecialist(_SpecialistBase):
    agent_name = "corporate_records_specialist"
    schema = CORPORATE_RECORDS_SCHEMA

    def system_prompt(self) -> str:
        return get_prompt("corporate_records_specialist")


class DueDiligenceSpecialist(_SpecialistBase):
    agent_name = "due_diligence_specialist"
    schema = DUE_DILIGENCE_SCHEMA

    def system_prompt(self) -> str:
        return get_prompt("due_diligence_specialist")


class CorrespondenceSpecialist(_SpecialistBase):
    agent_name = "correspondence_specialist"
    schema = CORRESPONDENCE_SCHEMA

    def system_prompt(self) -> str:
        return get_prompt("correspondence_specialist")


class ComplianceFilingSpecialist(_SpecialistBase):
    agent_name = "compliance_specialist"
    schema = COMPLIANCE_FILING_SCHEMA

    def system_prompt(self) -> str:
        return get_prompt("compliance_specialist")


class CourtOpinionsSpecialist(_SpecialistBase):
    agent_name = "court_opinions_specialist"
    schema = COURT_OPINIONS_SCHEMA

    def system_prompt(self) -> str:
        return get_prompt("court_opinions_specialist")


# Specialist registry — maps doc_type keys to specialist classes
SPECIALIST_REGISTRY = {
    "contract": ContractsSpecialist,
    "corporate_record": CorporateRecordsSpecialist,
    "due_diligence": DueDiligenceSpecialist,
    "correspondence": CorrespondenceSpecialist,
    "compliance_filing": ComplianceFilingSpecialist,
    "court_opinion": CourtOpinionsSpecialist,
}


def get_specialist(doc_type: str, model: str | None = None, api_key: str | None = None) -> BaseAgent:
    """Get the specialist agent for a given document type.

    Args:
        doc_type: Document type key (e.g., "contract").
        model: Optional model override.
        api_key: Optional API key override.

    Returns:
        An instantiated specialist agent.

    Raises:
        ValueError: If no specialist exists for the doc_type.
    """
    if doc_type not in SPECIALIST_REGISTRY:
        raise ValueError(f"No specialist registered for doc_type: {doc_type}")
    return SPECIALIST_REGISTRY[doc_type](model=model, api_key=api_key)


class InsuranceClaimsSpecialist(_SpecialistBase):
    agent_name = "insurance_claims_specialist"
    schema = INSURANCE_CLAIMS_SCHEMA

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 prompt_version: str = "insurance_claims_specialist_v0",
                 callbacks: list | None = None):
        super().__init__(model=model, api_key=api_key, callbacks=callbacks)
        self.prompt_version = prompt_version
        self._last_chunked = False
        self._last_n_chunks = 0

    def system_prompt(self) -> str:
        return get_prompt(self.prompt_version)
