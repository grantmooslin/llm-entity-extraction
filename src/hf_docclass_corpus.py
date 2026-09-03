"""Direct Hugging Face data pipe for the hierarchical doc-class eval runner.

``run_langfuse_docclass_eval.py`` historically loads rows either from
Braintrust datasets or from local JSONL dumps exported by
``scripts/datasets/export_hf_docclass_merged.py``. This module removes the
intermediate export hop: :func:`load_hf_docclass_corpus` joins the corpus
repo's ``default`` config (blind ``doc_text`` / ``prompt`` / ``filename`` /
``metadata``) with its ``ground_truth`` config (labels + GT fields) on
``filename`` — the SAME join ``export_hf_docclass_merged.py`` performs — and
returns rows in the runner's expected shape plus source ``meta`` for the
run-record metadata.

Honesty rules mirror ``load_braintrust_dataset`` (``src/braintrust_utils.py``):
rows with an invalid expected class or empty document text are SKIPPED, never
fabricated, and the loader refuses to invent a ``filename`` (a row without one
cannot be joined to its ground truth and is dropped). ``meta`` carries the
requested ``repo`` / ``config`` / ``revision``, the emitted ``num_rows``, and
a content ``sha`` when the ``datasets`` library exposes per-shard download
checksums for the loaded config (``None`` otherwise — never guessed).

The ``datasets`` library is imported INSIDE the function (not at module
import) so tests can stub ``datasets.load_dataset`` with a fake module in
``sys.modules`` and exercise the loader network-free.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from typing import Any

DEFAULT_HF_DATASET = "Lucius-Morningstar/mailroom-corpus"
BLIND_CONFIG = "default"
DEFAULT_GT_CONFIG = "ground_truth"

INSURANCE_GT_KEYS = (
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
)

CLAUSE_GT_KEYS = ("cuad_clause_labels", "maud_clause_labels")


def _coerce_gt_value(raw):
    """Parse list-like GT strings from the Hub into Python values."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(s)
                except (SyntaxError, ValueError):
                    return raw
        return raw
    return raw


def _build_gt_fields(row: dict) -> dict:
    """Collect per-document GT fields the row carries (claims keys + clause labels)."""
    gf: dict = {}
    for key in INSURANCE_GT_KEYS + CLAUSE_GT_KEYS:
        if key in row and row[key] not in (None, ""):
            gf[key] = _coerce_gt_value(row[key])
    return gf


def _resolve_expected(gt_row: dict) -> str:
    """Resolve the doc_type label from the GT row (mirror of the Braintrust
    loader: a dict-valued ``expected`` falls back to ``doc_type`` / ``expected_doc_class``)."""
    raw = gt_row.get("expected")
    if raw is None:
        raw = gt_row.get("expected_doc_class") or gt_row.get("doc_type")
    if isinstance(raw, dict):
        raw = raw.get("doc_type") or raw.get("expected_doc_class") or ""
    return str(raw or "").strip()


def _resolve_expected_fields(gt_row: dict) -> dict:
    """``expected_fields`` when the GT carries them (dict-``expected`` or a top-level column)."""
    raw = gt_row.get("expected")
    if isinstance(raw, dict):
        ef = raw.get("expected_fields")
        if ef:
            return dict(ef) if isinstance(ef, dict) else {}
    ef = gt_row.get("expected_fields")
    return dict(ef) if isinstance(ef, dict) else {}


def _coerce_metadata(raw) -> dict:
    """Blind-side metadata: JSON strings are parsed; anything else stays a dict."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return dict(raw or {})


def _iter_rows(loaded) -> list[dict]:
    """Flatten a ``load_dataset`` result (DatasetDict or Dataset) to row dicts.

    A DatasetDict is a ``Mapping`` (split name -> Dataset), a Dataset is not —
    distinguishing on ``Mapping`` handles both the real library and the
    plain-dict test stub.
    """
    if isinstance(loaded, Mapping):
        rows: list[dict] = []
        for split in loaded.values():
            rows.extend(split)
        return rows
    return list(loaded)


def _resolved_sha(loaded: list) -> str | None:
    """Best-effort content sha of the loaded config.

    When the ``datasets`` library exposes per-shard download checksums
    (``Dataset.info.download_checksums`` — present on Hub parquet loads), fold
    every file's checksum into one sha256. Anything missing degrades to
    ``None`` — a resolved sha is recorded only when genuinely obtainable,
    never guessed.
    """
    digests: list[str] = []
    for obj in loaded:
        info = getattr(obj, "info", None)
        checksums = getattr(info, "download_checksums", None) or {}
        if not checksums:
            return None
        for path in sorted(checksums):
            spec = checksums[path]
            digest = spec.get("checksum") if isinstance(spec, dict) else spec
            if not digest:
                return None
            digests.append(f"{path}:{digest}")
    if not digests:
        return None
    h = hashlib.sha256()
    for d in digests:
        h.update(d.encode("utf-8"))
    return h.hexdigest()


def load_hf_docclass_corpus(
    repo: str = DEFAULT_HF_DATASET,
    config: str = DEFAULT_GT_CONFIG,
    revision: str | None = None,
    valid_classes: set[str] | None = None,
) -> tuple[list[dict], dict]:
    """Load the merged docclass corpus directly from the Hugging Face Hub.

    Joins the repo's ``default`` config (blind ``doc_text`` / ``prompt`` /
    ``filename`` / ``metadata``) with the ground-truth config ``config``
    (labels + GT fields) on ``filename`` — mirroring
    ``scripts/datasets/export_hf_docclass_merged.py``. Every returned row
    carries the runner's expected shape:

    ``{doc_text, prompt, filename, expected, expected_subclass, metadata,
    expected_fields, gt_fields, split}`` — plus ``expected_output`` when the
    GT row carries one.

    Honesty rules (mirror of ``load_braintrust_dataset``): rows whose
    ``expected`` label is not in ``valid_classes`` (or resolves to empty) and
    rows with empty ``doc_text`` are skipped — never fabricated. ``filename``
    is the stable per-row identity taken verbatim from the source row; a row
    without one cannot be joined to its GT and is dropped.

    Returns ``(rows, meta)`` where ``meta`` = ``{repo, config, revision,
    num_rows, sha}`` for the run-record metadata (``sha`` is ``None`` when not
    obtainable). ``datasets.load_dataset`` is imported inside this function so
    tests can stub it with a fake ``datasets`` module.
    """
    from datasets import load_dataset

    blind_ds = load_dataset(repo, BLIND_CONFIG, revision=revision)
    gt_ds = load_dataset(repo, config, revision=revision)
    blind = _iter_rows(blind_ds)
    gt = _iter_rows(gt_ds)

    gt_by_name: dict[str, dict] = {}
    for gt_row in gt:
        name = str(gt_row.get("filename") or "")
        if name:
            gt_by_name.setdefault(name, gt_row)

    rows: list[dict] = []
    for row in blind:
        filename = str(row.get("filename") or "")
        gt_row = gt_by_name.get(filename)
        if gt_row is None:
            continue
        expected = _resolve_expected(gt_row)
        if not expected or (valid_classes is not None and expected not in valid_classes):
            continue
        doc_text = str(row.get("doc_text") or "")
        if not doc_text.strip():
            continue
        rows.append({
            "doc_text": doc_text,
            "prompt": str(row.get("prompt") or ""),
            "filename": filename,
            "expected": expected,
            "expected_subclass": gt_row.get("expected_subclass") or None,
            "metadata": _coerce_metadata(row.get("metadata")),
            "expected_fields": _resolve_expected_fields(gt_row),
            "gt_fields": _build_gt_fields(gt_row),
            "split": str(gt_row.get("split") or row.get("split") or ""),
            **({"expected_output": gt_row["expected_output"]}
               if gt_row.get("expected_output") is not None else {}),
        })

    meta: dict[str, Any] = {
        "repo": repo,
        "config": config,
        "revision": revision,
        "num_rows": len(rows),
        "sha": _resolved_sha([blind_ds, gt_ds]),
    }
    return rows, meta