"""Correspondence-only eval primitives (KANBAN-103).

Join, filter, stratify, and score the Enron correspondence surface so the
runner's predicted fields line up with the Hugging Face ``ground_truth``
config:

    expected              -> predicted doc_type
    expected_subclass     -> predicted doc_subclass
    sentiment_label       -> predicted sentiment_label
    sentiment_score       -> predicted sentiment_score

No Hugging Face / network imports live here — the Hub loader sits in
``scripts/datasets/load_enron_correspondence.py`` so the core package stays
free of the datasets extra.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from agents.sorter_agent import (
    SENTIMENT_LABELS,
    SENTIMENT_SCORE_BAND,
    normalize_doc_subclass,
    normalize_sentiment_label,
    normalize_sentiment_score,
    sentiment_label_from_score,
)

CORRESPONDENCE_DOC_TYPE = "correspondence"

# Predicted keys the sorter must emit; GT keys they are scored against.
PREDICTED_FIELDS = (
    "doc_type",
    "doc_subclass",
    "sentiment_label",
    "sentiment_score",
)
GT_FIELDS = (
    "expected",
    "expected_subclass",
    "sentiment_label",
    "sentiment_score",
)


def compose_doc_text(subject: str | None, text: str | None) -> str:
    """Build the sorter input: subject header + body (emails are short)."""
    subject = str(subject or "").strip()
    body = str(text or "").strip()
    if subject and body:
        return f"Subject: {subject}\n\n{body}"
    return body or subject


def join_blind_and_gt(
    blind_rows: list[dict],
    gt_rows: list[dict],
    *,
    correspondence_only: bool = True,
) -> list[dict]:
    """Join agent-blind rows to GT on ``filename`` (1:1).

    Blind rows carry ``text`` / ``subject`` and MUST NOT carry answer keys.
    GT rows carry ``expected``, ``expected_subclass``, sentiment, topic.
    Rows whose ``expected`` is not ``correspondence`` are dropped when
    ``correspondence_only`` is True (this eval is correspondence-only).
    """
    gt_by_name = {str(r.get("filename") or ""): r for r in gt_rows}
    joined: list[dict] = []
    for blind in blind_rows:
        filename = str(blind.get("filename") or "")
        gt = gt_by_name.get(filename)
        if not gt:
            continue
        expected = str(gt.get("expected") or "").strip()
        if correspondence_only and expected != CORRESPONDENCE_DOC_TYPE:
            continue
        text = compose_doc_text(blind.get("subject"), blind.get("text") or blind.get("doc_text"))
        if not text.strip():
            continue
        joined.append({
            "filename": filename,
            "doc_text": text,
            "subject": str(blind.get("subject") or ""),
            "expected": expected or CORRESPONDENCE_DOC_TYPE,
            "expected_subclass": gt.get("expected_subclass"),
            "sentiment_score": normalize_sentiment_score(gt.get("sentiment_score")),
            "sentiment_label": normalize_sentiment_label(gt.get("sentiment_label")),
            "content_topic": gt.get("content_topic"),
            "label_evidence": gt.get("label_evidence"),
            "sentiment_evidence": gt.get("sentiment_evidence"),
            "split": gt.get("split") or blind.get("split"),
            "metadata": dict(blind.get("metadata") or {}),
        })
    return joined


def filter_correspondence(rows: list[dict]) -> list[dict]:
    """Keep rows whose gold primary class is correspondence."""
    return [r for r in rows if str(r.get("expected") or "").strip() == CORRESPONDENCE_DOC_TYPE]


def stratified_by_subclass(
    dataset: list[dict],
    n: int,
    seed: int,
    *,
    key: str = "expected_subclass",
) -> list[dict]:
    """Sample ``n`` rows evenly across ``key`` (correspondence subclasses).

    Mirrors ``run_subtype_eval.stratified_sample``: every class with any rows
    gets at least one slot when ``n >= num_classes``; leftover budget goes to
    the largest classes. Tiny classes (e.g. attorney_demand, n=3 on the
    Hub dump) contribute every available row; unused slots redistribute.
    """
    if n <= 0:
        return []
    if n > len(dataset):
        n = len(dataset)
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in dataset:
        groups[str(row.get(key) or "other")].append(row)
    rng = random.Random(seed)
    selected: list[dict] = []
    remaining = n
    if remaining >= len(groups):
        for cls in sorted(groups):
            pick = rng.choice(groups[cls])
            groups[cls].remove(pick)
            selected.append(pick)
            remaining -= 1
    base, rem = divmod(remaining, max(1, len(groups)))
    order = sorted(groups, key=lambda k: len(groups[k]), reverse=True)
    for i, cls in enumerate(order):
        alloc = base + (1 if i < rem else 0)
        pool = groups[cls]
        if pool and alloc > 0:
            selected.extend(rng.sample(pool, min(alloc, len(pool))))
    if len(selected) < n:
        rest = [row for row in dataset if row not in selected]
        selected.extend(rng.sample(rest, min(n - len(selected), len(rest))))
    return selected[:n]


def append_missing_by_subclass(
    selected: list[dict],
    pool: list[dict],
    subclass: str,
    *,
    key: str = "expected_subclass",
    id_key: str = "filename",
) -> list[dict]:
    """Append pool rows of ``subclass`` whose id is not already selected.

    Keeps the original ``selected`` order, then adds missing extras sorted
    by filename so reruns are deterministic. Tiny classes (Hub
    ``attorney_demand`` n=3; full-corpus n=4) use this to force every
    example into the experiment sample instead of relying on the
    stratified leftover budget.
    """
    have = {str(r.get(id_key) or "") for r in selected}
    extras = [
        r for r in pool
        if str(r.get(key) or "") == subclass
        and str(r.get(id_key) or "")
        and str(r.get(id_key) or "") not in have
    ]
    extras.sort(key=lambda r: str(r.get(id_key) or ""))
    return list(selected) + extras


def merge_eval_rows(*groups: list[dict], id_key: str = "filename") -> list[dict]:
    """Concatenate row groups; the first occurrence of each filename wins."""
    out: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        for row in group:
            fn = str(row.get(id_key) or "")
            if not fn or fn in seen:
                continue
            seen.add(fn)
            out.append(row)
    return out


def read_gt_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """Load filename → field-patch rows from a JSONL override file.

    Each line is ``{"filename": "...", "expected_subclass": "...", ...}``.
    Only keys other than ``filename`` / ``reason`` are applied. Used to
    correct Hub GT without waiting on a republish (KANBAN-103).
    """
    overrides: dict[str, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            filename = str(row.get("filename") or "")
            if not filename:
                continue
            patch = {
                k: v for k, v in row.items()
                if k not in {"filename", "reason"} and v is not None
            }
            if patch:
                overrides[filename] = patch
    return overrides


def apply_gt_overrides(
    rows: list[dict],
    overrides: dict[str, dict[str, Any]],
    *,
    id_key: str = "filename",
) -> list[dict]:
    """Return a copy of ``rows`` with Hub GT patches applied in place of keys."""
    if not overrides:
        return list(rows)
    out: list[dict] = []
    for row in rows:
        filename = str(row.get(id_key) or "")
        patch = overrides.get(filename)
        if not patch:
            out.append(row)
            continue
        updated = dict(row)
        updated.update(patch)
        out.append(updated)
    return out


def read_filename_manifest(manifest_path: Path) -> list[str]:
    """Return filenames from a sample manifest, preserving file order."""
    wanted: list[str] = []
    with Path(manifest_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            fn = row.get("filename")
            if fn:
                wanted.append(str(fn))
    return wanted


def score_sentiment(
    predicted_score: float | None,
    predicted_label: str | None,
    expected_score: float | None,
    expected_label: str | None,
    *,
    band: float = SENTIMENT_SCORE_BAND,
) -> dict[str, Any]:
    """Score predicted sentiment against GT. Labels and scores are independent.

    ``sentiment_label_ok`` is exact match on the three-way label.
    ``sentiment_score_ok`` is True when both scores are present and
    ``|pred - gt| <= band``. MAE is the absolute residual (None if either
    score is missing).
    """
    pred_label = normalize_sentiment_label(predicted_label)
    exp_label = normalize_sentiment_label(expected_label)
    pred_score = normalize_sentiment_score(predicted_score)
    exp_score = normalize_sentiment_score(expected_score)
    if pred_label is None:
        pred_label = sentiment_label_from_score(pred_score)
    label_ok = (
        pred_label is not None and exp_label is not None and pred_label == exp_label
    )
    score_ok: bool | None
    mae: float | None
    if pred_score is None or exp_score is None:
        score_ok = None
        mae = None
    else:
        mae = abs(pred_score - exp_score)
        score_ok = mae <= band
    return {
        "sentiment_label": pred_label,
        "expected_sentiment_label": exp_label,
        "sentiment_score": pred_score,
        "expected_sentiment_score": exp_score,
        "sentiment_label_ok": label_ok if exp_label is not None else None,
        "sentiment_score_ok": score_ok,
        "sentiment_score_mae": mae,
        "sentiment_score_band": band,
    }


def predicted_aligns_with_gt(predicted: dict, expected: dict) -> dict[str, Any]:
    """Map sorter output onto the GT field assortment and flag mismatches.

    Used by tests and the runner so predicted variable names stay locked to
    the Hub ``ground_truth`` columns.
    """
    return {
        "doc_type": {
            "predicted": predicted.get("doc_type"),
            "expected": expected.get("expected"),
            "ok": predicted.get("doc_type") == expected.get("expected"),
        },
        "doc_subclass": {
            "predicted": predicted.get("doc_subclass"),
            "expected": expected.get("expected_subclass"),
            "ok": (
                normalize_doc_subclass(predicted.get("doc_subclass"), CORRESPONDENCE_DOC_TYPE)
                == normalize_doc_subclass(expected.get("expected_subclass"), CORRESPONDENCE_DOC_TYPE)
            ),
        },
        "sentiment_label": {
            "predicted": predicted.get("sentiment_label"),
            "expected": expected.get("sentiment_label"),
            "ok": (
                normalize_sentiment_label(predicted.get("sentiment_label"))
                == normalize_sentiment_label(expected.get("sentiment_label"))
            ),
        },
        "sentiment_score": {
            "predicted": predicted.get("sentiment_score"),
            "expected": expected.get("sentiment_score"),
            "ok": None,  # continuous — use score_sentiment
        },
    }


__all__ = [
    "CORRESPONDENCE_DOC_TYPE",
    "GT_FIELDS",
    "PREDICTED_FIELDS",
    "SENTIMENT_LABELS",
    "append_missing_by_subclass",
    "apply_gt_overrides",
    "compose_doc_text",
    "filter_correspondence",
    "join_blind_and_gt",
    "merge_eval_rows",
    "predicted_aligns_with_gt",
    "read_filename_manifest",
    "read_gt_overrides",
    "score_sentiment",
    "stratified_by_subclass",
]
