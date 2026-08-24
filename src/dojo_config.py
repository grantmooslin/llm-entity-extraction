"""llm-dojo-scoring settings wiring — maps the repo taxonomy into the package.

The ``llm_dojo_scoring`` package carries its own ``Settings`` object
(thresholds, equivalence sets, cost tables, failure modes) that defaults to
pure package defaults. This repo's ``config/taxonomy.yaml`` stays the local
source of truth, so this module bridges the two:

- ``field_scoring:`` block → the package ``FieldScoringSettings`` (same keys;
  ``embedding_enabled: true`` is honored — the package default is ``False``).
- ``cost_models:`` block → the package ``cost_models`` table. The YAML writes
  prices as dicts (``{input_per_million, output_per_million}``); the package
  accepts ``[input, output]`` lists only, so the dict form is converted here
  (the package otherwise SILENTLY ignores dict-form prices).
- ``gpu_hourly_usd:`` block → the package ``gpu_hourly_usd`` table for throughput
  cost comparison.
- Environment: the package's embedding rescue reads ``OPENROUTER_API_KEY`` /
  ``OPENROUTER_BASE_URL`` directly from ``os.environ``, while this repo keeps
  keys in ``config/environments/.env`` — ``load_env()`` runs first so the
  rescue works in eval runners and offline rescoring.

``LLM_DOJO_SCORING_CONFIG`` remains an escape hatch: when it points at an
existing YAML file, that file wins wholesale (its own ``field_scoring`` /
``cost_models`` blocks are honored) and the taxonomy mapping is skipped.
"""

from __future__ import annotations

import os

from llm_dojo_scoring import clear_settings_cache, configure
from llm_dojo_scoring import load_settings as _dojo_load_settings

from src.env_utils import load_env
from src.taxonomy import load_taxonomy

_FIELD_SCORING_DOTTED = {
    "ambiguous_band": "ambiguous_band",
    "bipartite_match_threshold": "bipartite_match_threshold",
    "embedding_enabled": "embedding_enabled",
    "embedding_model": "embedding_model",
    "embedding_rescue_below": "embedding_rescue_below",
    "partial_gt_fields": "partial_gt_fields",
    "containment_fields": "containment_fields",
}


def _coerce_field_scoring(fs: dict) -> dict:
    """Coerce YAML field-scoring values to the package's canonical types.

    The package's ``configure()`` sets values verbatim (no type coercion — that
    only happens in its YAML-file loader ``_apply_dict``). YAML round-trips
    lists as lists, so the repo must convert the ones the package stores as
    tuple/set: ``ambiguous_band`` -> ``(float, float)``, ``partial_gt_fields``
    and ``containment_fields`` -> ``set[str]``. Everything else arrives in the
    right type already (bool/float/str from the YAML scalar).
    """
    coerced = dict(fs)
    band = coerced.get("ambiguous_band")
    if isinstance(band, (list, tuple)) and len(band) == 2:
        coerced["ambiguous_band"] = (float(band[0]), float(band[1]))
    for key in ("partial_gt_fields", "containment_fields"):
        value = coerced.get(key)
        if value is not None:
            coerced[key] = {str(item) for item in value}
    return coerced


def _cost_models_from_yaml(fs_costs: dict) -> dict[str, tuple[float, float]]:
    """Convert the taxonomy's ``{model: {input_per_million, output_per_million}}``
    dict form into the package's ``{model: (input, output)}`` list form.

    The package ``_apply_dict`` only accepts 2-element lists/tuples and
    silently skips dict-form entries (verified against llm-dojo-scoring
    v0.1.0); this conversion keeps the repo's YAML format authoritative.
    """
    converted: dict[str, tuple[float, float]] = {}
    for model, prices in (fs_costs or {}).items():
        if isinstance(prices, (list, tuple)) and len(prices) == 2:
            converted[str(model)] = (float(prices[0]), float(prices[1]))
        elif isinstance(prices, dict):
            try:
                converted[str(model)] = (
                    float(prices["input_per_million"]),
                    float(prices["output_per_million"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
    return converted


def apply_taxonomy_settings() -> None:
    """Wire ``config/taxonomy.yaml`` into the package settings (idempotent).

    Called at import time by the compat/shim modules, so every eval runner,
    reporting script, and test gets the repo's thresholds before any package
    scoring call. Honors ``LLM_DOJO_SCORING_CONFIG`` when set (external file
    wins wholesale).
    """
    load_env()

    env_path = os.environ.get("LLM_DOJO_SCORING_CONFIG", "")
    if env_path.strip():
        _dojo_load_settings()  # cached env-file load; nothing to map
        return

    clear_settings_cache()
    taxonomy = load_taxonomy()

    overrides: dict = {}
    fs = _coerce_field_scoring(taxonomy.get("field_scoring") or {})
    for yaml_key, dotted_attr in _FIELD_SCORING_DOTTED.items():
        if yaml_key in fs:
            overrides[f"field_scoring__{dotted_attr}"] = fs[yaml_key]
    fv = fs.get("factuality_verification") or {}
    if "enabled" in fv:
        overrides["field_scoring__verification_enabled"] = fv["enabled"]
    if "token_coverage" in fv:
        overrides["field_scoring__verification_token_coverage"] = fv["token_coverage"]

    costs = _cost_models_from_yaml(taxonomy.get("cost_models") or {})
    if costs:
        overrides["cost_models"] = costs

    # GPU hourly pricing for throughput comparison
    gpu_costs = taxonomy.get("gpu_hourly_usd") or {}
    if gpu_costs:
        overrides["gpu_hourly_usd"] = {str(k): float(v) for k, v in gpu_costs.items()}

    if overrides:
        configure(**overrides)


# Wire at import so any module that imports the shims (or this one) gets the
# repo settings before the package's lru-cached defaults are consulted.
apply_taxonomy_settings()