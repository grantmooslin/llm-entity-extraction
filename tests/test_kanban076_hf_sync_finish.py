"""KANBAN-076: network-free pins for the HF family sync finish.

Pins the manifest-landmine repair (a bare root ``manifest.json`` gets ingested
by the Hub's JSON loader as a 1-row data table -> CastError on reconvert) so
NO publisher can ever stage one again, plus the single-source dedup/split
contracts of the deduplicated Enron publisher. Source-text inspection only —
no network, no HF calls at test time. Staging-data assertions are skipped
when the gitignored data/hf_export/ directory is absent.
"""

from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENRON_PUBLISHER = REPO_ROOT / "scripts" / "datasets" / "publish_enron_correspondence.py"
DEDUP_PUBLISHER = (
    REPO_ROOT / "scripts" / "datasets" / "publish_enron_correspondence_dedup.py"
)
KANBAN071_PUBLISHER = REPO_ROOT / "scripts" / "datasets" / "publish_kanban071.py"
DOCCLASS_BUILDER = REPO_ROOT / "scripts" / "datasets" / "build_docclass_merged.py"
ENRON_REPO_SCRIPTS = Path.home() / "Enron-Evaluation-Environment" / "scripts"
STAGING = REPO_ROOT / "data" / "hf_export"


def _src(path: Path) -> str:
    assert path.exists(), f"missing {path}"
    return path.read_text(encoding="utf-8")


# --- THE landmine rule: manifests ship as manifest.txt ONLY (no ".json" ---


def _assert_no_bare_manifest_staging(src: str, name: str):
    # the exact staging expression used by the 073/074 bug must not return
    assert '(tmpdir / "manifest.json")' not in src, (
        f"{name} stages a bare root manifest.json — Hub JSON loader ingests "
        f"it as data rows (CastError). Ship manifest.txt instead."
    )
    assert '(tmpdir / "manifest.json.txt")' not in src, (
        f"{name} stages manifest.json.txt — KANBAN-076 canaries proved the "
        f"Hub loader ingests ANY path containing '.json' (.json.txt included, "
        f"any subdir). Ship manifest.txt instead."
    )
    assert '"manifest.txt"' in src, (
        f"{name} does not stage manifest.txt"
    )


def test_enron_publisher_never_stages_bare_manifest_json():
    _assert_no_bare_manifest_staging(_src(ENRON_PUBLISHER), "publish_enron_correspondence")


def test_dedup_publisher_never_stages_bare_manifest_json():
    _assert_no_bare_manifest_staging(
        _src(DEDUP_PUBLISHER), "publish_enron_correspondence_dedup"
    )


def test_kanban071_publisher_never_stages_bare_manifest_json():
    _assert_no_bare_manifest_staging(_src(KANBAN071_PUBLISHER), "publish_kanban071")


def test_docclass_builder_manifest_is_loader_invisible():
    src = _src(DOCCLASS_BUILDER)
    # whatever it names its manifest artifact, no bare "manifest.json" literal
    assert '("manifest.json")' not in src.replace('("manifest.json.txt")', "")


# --- round 3: the metadata struct-cast landmine --------------------------


def _load_builder_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_docclass_merged", DOCCLASS_BUILDER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normalize_metadata_rows_union_and_scalarization():
    mod = _load_builder_module()
    rows = [
        {"metadata": {"a": "x", "n": {"k": [1, 2]}, "l": ["p", "q"]}},
        {"metadata": {"b": None, "a": "y"}},
        {},
    ]
    out = mod.normalize_metadata_rows([dict(r) for r in rows])
    keys = {frozenset(r["metadata"].keys()) for r in out}
    assert keys == {frozenset({"a", "b", "n", "l"})}, keys
    for r in out:
        for k, v in r["metadata"].items():
            # containers: JSON strings on carrying rows, "" on absent rows —
            # a key typed list/dict on ANY row must be string-typed on ALL
            if k in ("l", "n"):
                if r is out[0]:
                    assert isinstance(v, str), (k, type(v))
                    if k == "n":
                        assert v.startswith("{") and '"k"' in v
                    else:
                        assert v.startswith("[") and '"p"' in v
                else:
                    # missing keys become "" — never null, never a foreign type
                    assert v == ""
            else:
                assert isinstance(v, str), (k, type(v))
    # missing values become "" — never null
    assert out[2]["metadata"]["a"] == ""
    assert out[1]["metadata"]["b"] == ""


def test_normalize_metadata_rows_deterministic():
    import json as _json
    mod = _load_builder_module()
    rows = [{"metadata": {"z": 1, "n": {"b": 1, "a": 2}}}]
    outs = [mod.normalize_metadata_rows([dict(rows[0])])[0]["metadata"]["n"]
            for _ in range(2)]
    assert outs[0] == outs[1]
    assert outs[0].index('"a"') < outs[0].index('"b"')


def test_publisher_guard_rejects_heterogeneous_metadata():
    src = _src(KANBAN071_PUBLISHER)
    assert "md_keys" in src and "normalize_metadata_rows" in src, (
        "publish_kanban071 docclass path lost its KANBAN-076 metadata guard"
    )
    assert "len(md_keys) != 1" in src


# --- single-source contracts in the dedup publisher ----------------------


def test_dedup_imports_body_hash_from_enron_repo_dedupe_module():
    src = _src(DEDUP_PUBLISHER)
    assert "dedupe.py" in src                       # the shared module
    assert "body_hash" in src                       # the shared function
    # KANBAN-079: generic load_module() now serves dedupe + BOTH enrichment
    # labelers from ENRON_SCRIPTS — still loaded, never a local fork
    assert 'args.enron_scripts / "dedupe.py"' in src
    assert 'args.enron_scripts / "content_topics.py"' in src
    assert 'args.enron_scripts / "sentiment_scorer.py"' in src
    assert "Enron-Evaluation-Environment" in src    # never a local fork


def test_dedup_reuses_family_split_rule():
    src = _src(DEDUP_PUBLISHER)
    assert "from scripts.datasets.build_docclass_merged import assign_split" in src


def test_dedup_refuses_unverified_source_bytes():
    src = _src(DEDUP_PUBLISHER)
    assert "EXPECTED_SOURCE_SHA_PREFIX" in src      # integrity gate constant
    assert "refusing to build from" in src          # hard error on mismatch
    assert "0554a5973935" in src                    # the verified blob prefix


def test_dedup_pins_empty_body_and_first_occurrence_semantics():
    src = _src(DEDUP_PUBLISHER)
    # empty bodies are never duplicates of each other
    assert "empty_body_kept" in src
    # first occurrence wins -> deterministic output
    assert "seen.add(h)" in src


def test_dedup_keeps_schema_guard():
    src = _src(DEDUP_PUBLISHER)
    # KANBAN-079 widened the guard (enrichment validity added); refusal intact
    assert "fail the enrichment/schema guard" in src
    assert 'not in ("train", "test")' in src


def test_dedup_verifies_hub_lfs_sha_after_upload():
    src = _src(DEDUP_PUBLISHER)
    # KANBAN-079: PER-FILE LFS sha verification across both config views.
    # (LFS blobs compare the pointer's sha256; smaller files re-hash bytes.)
    assert "file_sha256" in src
    assert "lfs.sha256 == sha" in src
    assert "hexdigest() == sha" in src
    assert '"verified"' in src


# --- the upstream hash module itself (when the sibling repo is present) --


def _load_dedupe():
    mod_path = ENRON_REPO_SCRIPTS / "dedupe.py"
    if not mod_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("kanban076_dedupe", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upstream_body_hash_contract():
    mod = _load_dedupe()
    if mod is None:
        return  # sibling repo not checked out on this machine
    assert mod.body_hash("abc") == hashlib.md5(b"abc").hexdigest()
    assert mod.body_hash("héllo") == hashlib.md5("héllo".encode()).hexdigest()
    assert mod.body_hash("") is None                # empty bodies never hash


# --- staged artifacts (only when the gitignored staging dir exists) ------


def test_staged_dedup_export_exists_with_expected_shape():
    out = STAGING / "enron_correspondence_dedup.jsonl"
    stats = STAGING / "KANBAN076_DEDUP_STATS.json"
    if not stats.exists():
        return  # build not run on this machine
    import json

    m = json.loads(stats.read_text())
    assert m["rows"] + m["dropped_duplicates"] == m["source_rows"]
    assert m["source_rows"] == 517390
    assert m["empty_body_rows_kept"] == 0
    assert m["derived_from"]["verified_local_sha256"].startswith("0554a5973935")
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            first = json.loads(fh.readline())
        assert set(("filename", "text", "subject", "expected",
                    "expected_subclass", "label_evidence", "split",
                    "metadata")) <= set(first)
