"""KANBAN-105 network-free pins: docclass-merged v6 rebalance tooling.

Covers the three new dataset builders:

* ``build_correspondence_append`` — draw law (sha256-within-stratum order,
  quota + round-robin fill, determinism), doc_text mirror exactness vs the
  canonical ``src.correspondence_eval.compose_doc_text``;
* ``build_docclass_v6`` — fusion laws (corpus-rank order, family-split
  re-assertion, subclass canon, claims GT promotion + blind-surface leak
  strip, duplicate-filename guard);
* ``publish_docclass_v6`` — GT coercion law (strings-or-null) + blind
  metadata leak guard.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.datasets.build_correspondence_append import (
    compose_doc_text,
    stratified_draw,
)
from scripts.datasets.build_docclass_v6 import CORPUS_RANK


def _sha(filename: str) -> str:
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# draw law
# ---------------------------------------------------------------------------

def _pool(subclass_sizes: dict[str, int]) -> list[dict]:
    rows = []
    for sub, n in subclass_sizes.items():
        for i in range(n):
            rows.append({"filename": f"{sub}/{i:04d}.",
                         "expected": "correspondence",
                         "expected_subclass": sub})
    return rows


def test_stratified_draw_quota_then_round_robin_fill():
    pool = _pool({"email": 100, "memo": 50, "attorney_demand": 2})
    drawn = stratified_draw(pool, 30, quota=8)
    by_sub: dict[str, list[str]] = {}
    for r in drawn:
        by_sub.setdefault(r["expected_subclass"], []).append(r["filename"])
    # quota 8 per stratum, tiny strata ship whole, round-robin fill tops up
    assert len(by_sub["attorney_demand"]) == 2
    assert len(by_sub["memo"]) >= 8
    assert len(drawn) == 30
    # within a stratum the draw takes the sha256-lowest filenames first
    memo_order = sorted(by_sub["memo"], key=_sha)
    pool_memo_order = sorted((r["filename"] for r in pool
                              if r["expected_subclass"] == "memo"), key=_sha)
    assert memo_order == pool_memo_order[:len(memo_order)]


def test_stratified_draw_is_deterministic():
    pool = _pool({"email": 20, "letter": 15})
    first = [r["filename"] for r in stratified_draw(pool, 12, quota=4)]
    second = [r["filename"] for r in stratified_draw(pool, 12, quota=4)]
    assert first == second


def test_stratified_draw_pool_exhaustion_bounded():
    pool = _pool({"email": 5})
    drawn = stratified_draw(pool, 50, quota=10)
    assert len(drawn) == 5


def test_compose_doc_text_mirror_is_exact():
    from src.correspondence_eval import compose_doc_text as canonical

    cases = [("Subj line", "body text"), ("", "body only"),
             ("subject only", None), (None, None), ("  padded  ", "  x  ")]
    for subject, text in cases:
        assert compose_doc_text(subject, text) == canonical(subject, text)


# ---------------------------------------------------------------------------
# fusion laws (synthetic parent + appends)
# ---------------------------------------------------------------------------

def _write_parent(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    blind_dir = tmp_path / "default"
    gt_dir = tmp_path / "ground_truth"
    blind_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)
    blind_cols = ["filename", "doc_text", "prompt", "metadata"]
    gt_extra = ["label_evidence", "sentiment_score", "intent",
                "subject_matter", "keywords"]
    for split in ("train", "test"):
        subset = [r for r in rows if r["split"] == split]
        pq.write_table(pa.Table.from_pylist([
            {"filename": r["filename"], "doc_text": r["doc_text"],
             "prompt": "", "metadata": r["metadata"]} for r in subset]),
            blind_dir / f"{split}-00000-of-00001.parquet")
        gt_rows = []
        for r in subset:
            gt_rows.append({
                "filename": r["filename"], "expected": r["expected"],
                "expected_subclass": r["expected_subclass"],
                "split": r["split"],
                **{k: r.get("gt_fields", {}).get(k) for k in gt_extra}})
        pq.write_table(pa.Table.from_pylist(gt_rows),
                       gt_dir / f"{split}-00000-of-00001.parquet")
    return blind_dir, gt_dir


def _append_jsonl(path: Path, rows: list[dict]) -> Path:
    """Fixture writer — splits are recomputed via the family law so every
    append row's declared split matches md5(filename) % 10."""
    from scripts.datasets.build_docclass_merged import assign_split

    for r in rows:
        r["split"] = assign_split(str(r["filename"]))
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _parent_rows() -> list[dict]:
    return [
        {"filename": "contract_a.pdf", "doc_text": "contract text",
         "expected": "contract", "expected_subclass": "service",
         "split": "train", "metadata": {"source_dataset": "cuad"}},
        {"filename": "corr_old/1.", "doc_text": "old email",
         "expected": "correspondence", "expected_subclass": "email",
         "split": "train", "metadata": {"source_dataset": "dedup"},
         "gt_fields": {"intent": "update", "subject_matter": "s.",
                       "keywords": '["k"]'}},
        {"filename": "claim_old/carrier_1.txt", "doc_text": "old eob",
         "expected": "insurance_claim", "expected_subclass": "carrier",
         "split": "test", "metadata": {"source_dataset": "cms"},
         "gt_fields": {"claim_number": "C1"}},
    ]


def test_build_v6_corpus_rank_order_and_gf_join(tmp_path):
    from scripts.datasets.build_docclass_v6 import build_v6, load_parent

    blind_dir, gt_dir = _write_parent(tmp_path, _parent_rows())
    parent = load_parent(blind_dir, gt_dir)
    assert len(parent) == 3
    # purpose GT preserved from the train shard; absent keys -> missing
    corr_old = next(r for r in parent if r["filename"] == "corr_old/1.")
    assert corr_old["gt_fields"]["intent"] == "update"

    corr_append = _append_jsonl(tmp_path / "corr.jsonl", [
        {"filename": "corr_new/2.", "doc_text": "new email",
         "expected": "correspondence", "expected_subclass": "email",
         "split": "train", "gt_fields": {"sentiment_score": 0.5},
         "metadata": {"custodian": "x"}},
        {"filename": "corr_new/1.", "doc_text": "newer email",
         "expected": "correspondence", "expected_subclass": "email",
         "split": "test", "gt_fields": {}, "metadata": {}},
    ])
    ins_append = _append_jsonl(tmp_path / "ins.jsonl", [
        {"filename": "claim_new/pde_1.txt", "doc_text": "new eob",
         "expected": "insurance_claim", "expected_subclass": "pde",
         "split": "train",
         "metadata": {"record_id": "pde:pde_1",
                      "ground_truth": {"claim_number": "P1",
                                       "claimed_amount": 12.5}}},
    ])
    from scripts.datasets.build_docclass_v6 import load_append

    corr = load_append(corr_append, "correspondence")
    ins = load_append(ins_append, "insurance_claim")
    # claims GT promoted out of metadata (v5 law) — blind surface stays clean
    assert ins[0]["gt_fields"]["claim_number"] == "P1"
    assert "ground_truth" not in ins[0]["metadata"]

    merged = build_v6(parent, corr, ins)
    order = [r["filename"] for r in merged]
    ranks = [CORPUS_RANK[r["expected"]] for r in merged]
    assert ranks == sorted(ranks), f"corpus rank violated: {order}"
    # filename-sorted within rank: new correspondence interleaves with old
    corr_order = [f for f in order if f.startswith("corr_")]
    assert corr_order == ["corr_new/1.", "corr_new/2.", "corr_old/1."]


def test_build_v6_rejects_duplicate_and_bad_split(tmp_path):
    from scripts.datasets.build_docclass_v6 import load_append

    dup = _append_jsonl(tmp_path / "dup.jsonl", [
        {"filename": "corr_old/1.", "doc_text": "x",
         "expected": "correspondence", "expected_subclass": "email",
         "split": "train", "gt_fields": {}, "metadata": {}}])
    with pytest.raises(AssertionError, match="duplicate filenames"):
        from scripts.datasets.build_docclass_v6 import build_v6, load_parent

        blind_dir, gt_dir = _write_parent(tmp_path / "p2", _parent_rows())
        build_v6(load_parent(blind_dir, gt_dir),
                 load_append(dup, "correspondence"), [])

    bad_split = tmp_path / "bad.jsonl"
    bad_split.write_text(json.dumps({
        "filename": "zzz/test_hash_48.", "doc_text": "x",
        "expected": "correspondence", "expected_subclass": "email",
        "split": "train", "gt_fields": {}, "metadata": {}}) + "\n",
        encoding="utf-8")
    # force a family-rule mismatch: md5("zzz/test_hash_48.") % 10 == 0 -> test,
    # so the fixture's "train" split must be refused
    import hashlib as _h

    assert int(_h.md5(b"zzz/test_hash_48.").hexdigest(), 16) % 10 == 0
    with pytest.raises(AssertionError, match="family rule"):
        load_append(bad_split, "correspondence")


# ---------------------------------------------------------------------------
# publish-side coercion + leak guards
# ---------------------------------------------------------------------------

def test_publish_v6_gt_row_coercion_strings_or_null():
    from scripts.datasets.publish_docclass_v6 import GT_COLUMNS, _gt_row

    row = {"filename": "f.txt", "expected": "insurance_claim",
           "expected_subclass": "pde", "split": "train",
           "gt_fields": {"claimed_amount": 12.5, "sentiment_score": 0.5,
                         "intent": "claim_data_record", "adjuster": None}}
    out = _gt_row(row)
    assert out["claimed_amount"] == "12.5"
    assert out["intent"] == "claim_data_record"
    assert out["adjuster"] is None
    assert set(out) == set(GT_COLUMNS) | {"split"}


def test_original_file_mapping_is_cast_safe(tmp_path):
    from scripts.datasets.build_docclass_v6 import (
        build_v6, load_append, load_original_files, load_parent,
    )

    blind_dir, gt_dir = _write_parent(tmp_path / "p3", _parent_rows())
    parent = load_parent(blind_dir, gt_dir)
    corr = load_append(_append_jsonl(tmp_path / "c.jsonl", [
        {"filename": "corr_new/3.", "doc_text": "x",
         "expected": "correspondence", "expected_subclass": "email",
         "split": "train", "gt_fields": {}, "metadata": {}}]),
        "correspondence")
    mapping_path = tmp_path / "mapping.jsonl"
    mapping_path.write_text(json.dumps(
        {"filename": "contract_a.pdf",
         "original_file": "files/contract/Part_I/X.pdf"}) + "\n",
        encoding="utf-8")
    mapping = load_original_files(mapping_path)
    rows = build_v6(parent, corr, [])
    hit = miss = 0
    for r in rows:
        v = mapping.get(r["filename"], "")
        r["metadata"]["original_file"] = v
        hit += bool(v)
        miss += not v
    assert hit == 1 and miss == 3  # only the mapped contract row carries a path
    # the union normalizer must keep the key on every row, string-typed
    from scripts.datasets.build_docclass_merged import normalize_metadata_rows

    normalized = normalize_metadata_rows(rows)
    assert all(isinstance(r["metadata"].get("original_file"), str)
               for r in normalized)


def test_publish_v6_load_rejects_metadata_gt_leak(tmp_path):
    from scripts.datasets.publish_docclass_v6 import load_v6

    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "filename": "f.txt", "doc_text": "x", "prompt": "",
        "expected": "correspondence", "expected_subclass": "email",
        "split": "train", "gt_fields": {},
        "metadata": {"ground_truth": {"claim_number": "C"}}}) + "\n",
        encoding="utf-8")
    with pytest.raises(AssertionError, match="GT keys leaked"):
        load_v6(bad)


def test_publish_v6_strips_label_equivalents_from_metadata():
    """v6 blind-surface repair: the v4-era metadata label rides (stripped),
    answer payloads never rode in metadata, non-label keys survive intact."""
    from scripts.datasets.publish_docclass_v6 import strip_blind_labels

    rows = [{"filename": f"f{i}.txt",
             "metadata": {"expected_doc_type": "correspondence",
                          "expected_subclass": "email",
                          "custodian": "x"}} for i in range(2)]
    assert strip_blind_labels(rows) == 2
    assert all(r["metadata"] == {"custodian": "x"} for r in rows)
    # idempotent: a clean row passes through with count 0
    clean = [{"filename": "g.txt", "metadata": {"custodian": "y"}}]
    assert strip_blind_labels(clean) == 0
    assert clean[0]["metadata"] == {"custodian": "y"}
