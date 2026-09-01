"""Shared Braintrust HTTP, dataset, and experiment helpers.

Used by the dataset streamers (``scripts/datasets/``), the eval runners
(``scripts/eval/``), and the report generators (``scripts/reporting/``) so the
Braintrust wire protocol (experiment fetch, dataset loading, experiment
listing) lives in one place.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from src.taxonomy import doc_class_keys

VALID_CLASSES = doc_class_keys()
EXPERIMENT_FETCH_RETRIES = 6
EXPERIMENT_FETCH_LIMIT = 1000  # events per paginated fetch (API supports up to 1000)


# ---------------------------------------------------------------------------
# Experiment + dataset HTTP helpers
# ---------------------------------------------------------------------------


def _v1_api_base(api_base: str) -> str:
    """Ensure an api_base points at the REST endpoints under ``/v1``."""
    api_base = api_base.rstrip("/")
    return f"{api_base}/v1" if not api_base.endswith("/v1") else api_base


def completion_prompt_content(prompt_obj: dict | None) -> str | None:
    """Return the text body of a Braintrust completion prompt, or None."""
    if not prompt_obj:
        return None
    prompt_data = prompt_obj.get("prompt_data") or {}
    block = prompt_data.get("prompt") or {}
    if block.get("type") == "completion":
        return block.get("content")
    return None


def get_prompt_by_slug(
    api_key: str,
    project_id: str,
    slug: str,
    api_base: str = "https://api.braintrust.dev/v1",
) -> dict | None:
    """Return the latest prompt object for ``slug`` in a project, or None."""
    resp = requests.get(
        f"{_v1_api_base(api_base)}/prompt",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"project_id": project_id, "slug": slug},
        timeout=60,
    )
    resp.raise_for_status()
    objects = resp.json().get("objects") or []
    return objects[0] if objects else None


def upsert_completion_prompt(
    api_key: str,
    project_id: str,
    slug: str,
    content: str,
    *,
    name: str | None = None,
    description: str = "",
    api_base: str = "https://api.braintrust.dev/v1",
) -> dict:
    """Create or replace a completion-type prompt in the Braintrust registry."""
    body = {
        "project_id": project_id,
        "name": name or slug,
        "slug": slug,
        "description": description or f"Versioned prompt {slug}",
        "prompt_data": {"prompt": {"type": "completion", "content": content}},
    }
    resp = requests.put(
        f"{_v1_api_base(api_base)}/prompt",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def list_experiments(api_key: str, project_id: str, api_base: str = "https://api.braintrust.dev/v1") -> list[dict]:
    """Return metadata for every experiment in a project."""
    resp = requests.get(
        f"{_v1_api_base(api_base)}/experiment",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"project_id": project_id, "limit": 200},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("objects", [])


def list_datasets(api_key: str, project_id: str, api_base: str = "https://api.braintrust.dev/v1") -> list[dict]:
    """Return metadata for every dataset in a project."""
    resp = requests.get(
        f"{_v1_api_base(api_base)}/dataset",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"project_id": project_id, "limit": 200},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("objects", [])


def dataset_exists(api_key: str, project_id: str, name: str, api_base: str = "https://api.braintrust.dev/v1") -> bool:
    """Return True when a dataset with ``name`` exists in the project."""
    return any(d.get("name") == name for d in list_datasets(api_key, project_id, api_base))


def delete_dataset_by_name(
    api_key: str,
    project_id: str,
    name: str,
    api_base: str = "https://api.braintrust.dev/v1",
) -> str | None:
    """Delete a dataset by name if it exists; return its id or None."""
    headers = {"Authorization": f"Bearer {api_key}"}
    for dataset in list_datasets(api_key, project_id, api_base):
        if dataset.get("name") == name:
            dataset_id = dataset["id"]
            resp = requests.delete(f"{_v1_api_base(api_base)}/dataset/{dataset_id}", headers=headers, timeout=60)
            resp.raise_for_status()
            return dataset_id
    return None


def fetch_experiment_rows(
    api_key: str,
    experiment_id: str,
    api_base: str = "https://api.braintrust.dev/v1",
    max_retries: int = EXPERIMENT_FETCH_RETRIES,
    timeout: int = 300,
) -> list[dict]:
    """Fetch every event (span) of an experiment, retrying on rate limits."""
    headers = {"Authorization": f"Bearer {api_key}"}
    rows: list[dict] = []
    cursor = None
    while True:
        body = {"limit": EXPERIMENT_FETCH_LIMIT}
        if cursor:
            body["cursor"] = cursor
        resp = None
        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    f"{_v1_api_base(api_base)}/experiment/{experiment_id}/fetch",
                    headers=headers,
                    json=body,
                    timeout=timeout,
                )
                resp.raise_for_status()
                break
            except requests.exceptions.HTTPError as e:
                if resp is not None and resp.status_code == 429 and attempt < max_retries - 1:
                    wait = min(30, 10 * (2 ** attempt))
                    print(f"  Rate limited, waiting {wait}s (retry {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                elif attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    print(f"  Retry {attempt + 1}/{max_retries} after {wait}s ({e})")
                    time.sleep(wait)
                else:
                    raise
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait = 10 * (attempt + 1)
                    print(f"  Timeout, retry {attempt + 1}/{max_retries} after {wait}s")
                    time.sleep(wait)
                else:
                    raise
        data = resp.json()
        batch = data.get("events", [])
        rows.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
    return rows


def find_experiment_by_name(api_key: str, project_id: str, name: str, api_base: str = "https://api.braintrust.dev/v1") -> dict | None:
    """Return experiment metadata for the experiment with ``name`` (or None)."""
    for exp in list_experiments(api_key, project_id, api_base):
        if exp.get("name") == name:
            return exp
    return None


def resolve_prompt_version(experiment_meta: dict) -> str:
    """Return the prompt version (e.g. ``sorter_v0``) for an experiment.

    Prefers the experiment's ``metadata.prompt_version``, then parses the
    version out of the experiment name (``qwen3.7-flash_sorter_v0``).
    """
    metadata = experiment_meta.get("metadata") or {}
    version = metadata.get("prompt_version")
    if version:
        return str(version)
    match = re.search(r"_p(v?\d+(?:\.\d+)?|[a-z0-9_]+)$", experiment_meta.get("name") or "")
    return match.group(1) if match else "unknown"


# ---------------------------------------------------------------------------
# Dataset loading (text documents)
# ---------------------------------------------------------------------------


def _deterministic_record_id(record: dict) -> str:
    """Derive a deterministic Braintrust dataset row id from a record.

    Content-addressed over the canonical JSON of the full record, so (a) a
    rerun of a streamer lands on the SAME ids and upserts in place, and
    (b) a changed record (new metadata, different expected label) gets a new
    id instead of silently overwriting. Braintrust's ``Dataset.insert``
    assigns a fresh random UUID when no id is passed, which would append
    duplicate rows on every rerun.
    """
    import hashlib
    import json as _json

    blob = _json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)  # KANBAN-088-EXEMPT: hash input — byte-stability beats split-safety; never persisted as JSONL rows
    return "rec-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def load_braintrust_dataset(
    project: str,
    dataset_name: str,
    dataset_api_key: str | None = None,
    valid: set[str] | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """Load a text-document Braintrust dataset into eval records.

    Returns ``[{doc_text, prompt, filename, expected}]`` where the expected
    value is a class label. Rows without a label or document text are skipped.
    ``valid`` restricts accepted expected labels (default: the taxonomy doc
    classes; pass the task's classes for LegalBench task datasets).
    ``project_id`` pins the project when the name alone is ambiguous (datasets
    synced via ``upload_text_dataset`` are keyed by project id).
    """
    import braintrust

    valid = valid or set(VALID_CLASSES)

    api_key = dataset_api_key or os.environ.get("BRAINTRUST_API_KEY")
    if api_key:
        braintrust.login(api_key=api_key)

    dataset = braintrust.init_dataset(
        project_id=project_id, project=project, name=dataset_name
    )
    records: list[dict] = []
    for i, row in enumerate(dataset):
        expected_raw = row.get("expected")
        expected_fields = {}
        clause_labels = []
        if isinstance(expected_raw, dict):
            expected = expected_raw.get("doc_type") or expected_raw.get("expected_doc_class")
            expected_fields = expected_raw.get("expected_fields") or {}
            clause_labels = expected_raw.get("clause_labels") or []
        else:
            expected = expected_raw
        expected = str(expected or "").strip()
        if expected not in valid:
            continue

        input_data = row.get("input") or {}
        if isinstance(input_data, str):
            doc_text = input_data
            prompt = ""
        elif isinstance(input_data, dict):
            doc_text = input_data.get("doc_text") or input_data.get("text") or ""
            prompt = input_data.get("prompt") or ""
        else:
            doc_text = ""
            prompt = ""
        doc_text = str(doc_text or "")
        if not doc_text.strip() and not prompt.strip():
            continue

        metadata = dict(input_data.get("metadata") or {}) if isinstance(input_data, dict) else {}
        # Stable per-document identity: the CUAD stem (document_id / source
        # file) whenever the dataset carries it, so the SAME contract always
        # gets the SAME filename across runs and re-synced datasets (index-
        # based names like "document_12" depend on row order, which Braintrust
        # does not guarantee).
        filename = input_data.get("filename") if isinstance(input_data, dict) else ""
        if not filename:
            filename = (metadata.get("document_id") or "").strip() or \
                       Path(str(metadata.get("source_file") or "")).stem or \
                       f"document_{i + 1}"
        records.append({
            "doc_text": doc_text,
            "prompt": prompt,
            "filename": str(filename),
            "expected": expected,
            "metadata": metadata,
            "expected_output": row.get("expected_output") or {},
            "expected_fields": expected_fields,
            "clause_labels": clause_labels,
        })
    return records


def upload_text_dataset(
    records: list[dict],
    project_id: str,
    dataset_name: str,
    api_key: str,
    *,
    description: str = "",
    metadata: dict | None = None,
    experiment_name: str | None = None,
    on_progress=None,
) -> dict:
    """Insert text-document records into a Braintrust dataset.

    Each record: ``{"input": {...}, "expected": ..., "metadata": {...}}``.
    Returns ``{"inserted": n, "failed": m, "failure_details": [...]}`` and
    logs one summary experiment row (``create-<dataset>``) so dataset
    creation is traceable in the project.

    Rows carry a DETERMINISTIC id derived from the record's content
    (``_deterministic_record_id``), so reruns UPSERT in place instead of
    appending duplicate rows — Braintrust's ``insert`` otherwise assigns a
    fresh random UUID per call.
    """
    import braintrust

    braintrust.login(api_key=api_key)
    dataset = braintrust.init_dataset(project_id=project_id, name=dataset_name)
    metadata = dict(metadata or {})
    metadata.update({"dataset": dataset_name, "records": len(records)})

    experiment = braintrust.init_experiment(
        project_id=project_id,
        experiment=experiment_name or f"create-{dataset_name}",
        description=description or f"Build text dataset '{dataset_name}'",
        metadata={"task": "dataset_creation", "dataset": dataset_name, **metadata},
    )

    inserted = failed = 0
    failures: list[str] = []
    for i, record in enumerate(records):
        try:
            dataset.insert(
                input=record["input"],
                expected=record["expected"],
                metadata=record.get("metadata", {}),
                id=_deterministic_record_id(record),
            )
            inserted += 1
        except Exception as exc:  # noqa: BLE001 - one bad row shouldn't abort
            failed += 1
            failures.append(f"{record.get('input', {}).get('filename', i)}: {exc}")
        if on_progress and (i + 1) % 25 == 0:
            on_progress(i + 1, len(records))

    dataset.flush()
    dataset.close()

    experiment.log(
        input={"dataset": dataset_name, "records": len(records)},
        output={"inserted": inserted, "failed": failed},
        scores={"insertion_rate": inserted / max(1, len(records)),
                "failure_rate": failed / max(1, len(records))},
        metrics={"records": inserted, "failed": failed},
        metadata={"failures": failures[:50]},
    )
    experiment.close()

    return {"inserted": inserted, "failed": failed, "failures": failures}


def fetch_attachment_bytes(
    api_key: str,
    reference: dict,
    org_id: str,
    api_base: str = "https://api.braintrust.dev",
    retries: int = 3,
) -> bytes:
    """Download an already-uploaded Braintrust attachment's bytes directly.

    Transient object-store read timeouts are retried with linear backoff so a
    single slow S3 response never drops a row from an evaluation. Ported from
    the RVL-CDIP classifier repo.
    """
    params = {
        "filename": reference["filename"],
        "content_type": reference["content_type"],
        "org_id": org_id,
    }
    if reference["type"] == "braintrust_attachment":
        params["key"] = reference["key"]
    elif reference["type"] == "external_attachment":
        params["url"] = reference["url"]
    else:
        raise RuntimeError(f"Unknown attachment type: {reference['type']}")

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                f"{api_base.rstrip('/')}/attachment",
                params=params,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60,
            )
            resp.raise_for_status()
            download_url = resp.json()["downloadUrl"]

            data = requests.get(download_url, timeout=120)
            data.raise_for_status()
            return data.content
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_error


def load_braintrust_image_dataset(
    project: str,
    dataset_name: str,
    dataset_api_key: str | None = None,
    org_id: str = "",
    api_base: str = "https://api.braintrust.dev",
    valid: set[str] | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """Load a Braintrust dataset's image attachments as base64 records.

    Returns ``[{image_b64, filename, expected, page, category}]``. Rows without
    a stored attachment (placeholder rows) or an invalid label are skipped.
    ``valid`` restricts accepted expected labels (default: the taxonomy doc
    classes). Attachments are downloaded in parallel. Ported from the
    RVL-CDIP repo.
    """
    import base64
    from concurrent.futures import ThreadPoolExecutor

    import braintrust

    valid = valid or set(VALID_CLASSES)
    api_key = dataset_api_key or os.environ.get("BRAINTRUST_API_KEY")
    if api_key:
        braintrust.login(api_key=api_key)

    dataset = braintrust.init_dataset(
        project_id=project_id, project=project, name=dataset_name
    )
    pending = []
    for i, row in enumerate(dataset):
        expected = row.get("expected")
        if isinstance(expected, dict):
            expected = expected.get("doc_type")
        expected = str(expected or "").strip()
        input_data = row.get("input") or {}
        if not isinstance(input_data, dict):
            continue
        metadata = input_data.get("metadata", {}) or {}
        attachment = input_data.get("image")
        page_attachments = input_data.get("pages") or []

        if metadata.get("placeholder", False) or expected not in valid:
            continue
        if not attachment and not page_attachments:
            continue

        def _filename_of(att):
            try:
                ref = getattr(att, "reference", None) or {}
                return ref.get("filename")
            except (KeyError, AttributeError):
                return None

        image_attachment = attachment or (page_attachments[0] if page_attachments else None)
        filename = _filename_of(image_attachment)
        if not filename:
            doc_id = input_data.get("document_id")
            filename = f"{doc_id or i + 1}.png"

        pending.append((expected, image_attachment, page_attachments, filename, metadata))

    records: list[dict] = []
    failures = []

    def grab(item):
        _, image_attachment, page_attachments, _, _ = item
        try:
            image_bytes = (
                fetch_attachment_bytes(api_key, image_attachment.reference, org_id, api_base)
                if image_attachment is not None else None
            )
            pages_bytes = [
                fetch_attachment_bytes(api_key, att.reference, org_id, api_base)
                for att in page_attachments
            ]
            return image_bytes, pages_bytes, None
        except Exception as exc:  # noqa: BLE001 - one bad row shouldn't abort the eval
            return None, [], str(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for (expected, _, _, filename, metadata), (image_bytes, pages_bytes, error) in zip(
            pending, pool.map(grab, pending)
        ):
            if error is not None:
                failures.append((expected, filename, error))
                continue
            record = {
                "filename": filename,
                "expected": expected,
                "page_count": len(pages_bytes) or (1 if image_bytes else 0),
                "category": metadata.get("category", ""),
                "document_id": metadata.get("document_id", ""),
            }
            if image_bytes is not None:
                record["image_b64"] = base64.b64encode(image_bytes).decode("utf-8")
            if pages_bytes:
                record["pages_b64"] = [
                    base64.b64encode(pb).decode("utf-8") for pb in pages_bytes
                ]
            records.append(record)

    for expected, filename, error in failures:
        print(f"SKIP {expected:<24} {filename}: {error}", file=sys.stderr)
    if failures:
        print(f"WARNING: skipped {len(failures)} rows with unreadable attachments", file=sys.stderr)

    return records


def load_experiment_task_rows(rows: list[dict]) -> list[dict]:
    """Extract per-task (root span) rows from a raw experiment fetch.

    Each returned dict has ``expected``, ``output``, ``input``, ``filename``,
    ``reasoning``, and ``metrics`` where available. Used by report generation.
    """
    tasks: list[dict] = []
    span_meta: dict[str, dict[str, Any]] = {}

    for row in rows:
        root = row.get("root_span_id") or row.get("span_id") or ""
        metadata = row.get("metadata") or {}
        if isinstance(metadata, dict) and (metadata.get("reasoning") or metadata.get("filename")):
            span_meta.setdefault(root, {}).update(metadata)

    for row in rows:
        output = row.get("output")
        if output is None or row.get("span_attributes") is not None and "task" not in (row.get("span_attributes") or {}):
            continue
        expected = row.get("expected")
        if expected is None:
            continue
        root = row.get("root_span_id") or row.get("span_id") or ""
        meta = dict(row.get("metadata") or {})
        meta.update(span_meta.get(root, {}))
        tasks.append({
            "expected": expected,
            "output": output,
            "input": row.get("input"),
            "filename": str(meta.get("filename") or "") or _filename_from_input(row.get("input")),
            "reasoning": str(meta.get("reasoning") or ""),
            "metrics": dict(row.get("metrics") or {}),
        })
    return tasks


def _filename_from_input(input_data: Any) -> str:
    if isinstance(input_data, dict):
        return str(input_data.get("filename") or "")
    return ""


# ---------------------------------------------------------------------------
# Misclassification analysis (for reports)
# ---------------------------------------------------------------------------


def find_misses(task_rows: list[dict]) -> list[dict]:
    """Return every scored-but-wrong task row.

    Each result dict has ``expected``, ``predicted``, ``filename``,
    ``reasoning``, and ``metrics``. Rows without a valid expected/output are
    skipped.
    """
    misses: list[dict] = []
    for row in task_rows:
        expected = row["expected"]
        output = row["output"]
        if expected not in VALID_CLASSES or not output:
            continue
        predicted = str(output).strip().lower()
        if predicted == expected:
            continue
        misses.append({
            "expected": expected,
            "predicted": predicted,
            "filename": row["filename"],
            "reasoning": row["reasoning"],
            "metrics": row["metrics"],
        })
    return misses
