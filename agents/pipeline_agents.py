"""Pipeline role agents — thin runnable wrappers over the vendored prompts.

The reviewer / boss / arbiter / reporter / transcriber roles live in the
llm-mailroom pipeline repo; upstream only carries their PROMPT constants.
These wrappers give the durability benches a uniform ``run(input) -> dict``
surface (structured JSON via ``BaseAgent._call_structured``) without
duplicating pipeline logic. Default prompt versions prefer the pilot-universe
docclass variants where they exist.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent, build_structured_schema
from src.prompts import get_prompt


class _StructuredAgent(BaseAgent):
    """run(user_message, schema) -> parsed dict via _call_structured."""

    # BaseAgent's llm()/logging seam reads agent_name; subclasses override.
    agent_name = "pipeline_role"

    prompt_version: str = ""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 prompt_version: str | None = None, callbacks: list | None = None):
        super().__init__(model=model, api_key=api_key, callbacks=callbacks)
        if prompt_version:
            self.prompt_version = prompt_version

    def system_prompt(self) -> str:
        return get_prompt(self.prompt_version)

    def run(self, user_message: str, json_schema: dict,
            temperature: float = 0.1, max_tokens: int | None = None) -> dict:
        return self._call_structured(
            user_message, json_schema=json_schema,
            system_prompt=self.system_prompt(),
            temperature=temperature, max_tokens=max_tokens or self._max_tokens,
        )


class ReviewerAgent(_StructuredAgent):
    """Blind second-opinion classifier (sorter_reviewer docclass lineage)."""

    agent_name = "sorter_reviewer"

    def __init__(self, model=None, api_key=None, callbacks=None,
                 prompt_version: str = "reviewer_docclass_pilot_v0"):
        super().__init__(model=model, api_key=api_key,
                         prompt_version=prompt_version, callbacks=callbacks)

    def run(self, user_message: str, json_schema: dict,
            temperature: float = 0.1, max_tokens: int | None = None) -> dict:
        return super().run(user_message, json_schema, temperature, max_tokens)


class BossAgent(_StructuredAgent):
    agent_name = "boss"

    BOSS_SCHEMA = build_structured_schema({
        "decision": {"type": "string",
                     "enum": ["approved", "merged", "review"]},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    })

    def __init__(self, model=None, api_key=None, callbacks=None,
                 prompt_version: str = "boss_docclass_pilot_v0"):
        super().__init__(model=model, api_key=api_key,
                         prompt_version=prompt_version, callbacks=callbacks)


class ArbiterAgent(_StructuredAgent):
    agent_name = "arbiter"

    ARBITER_SCHEMA = build_structured_schema({
        "action": {"type": "string",
                   "enum": ["accept_with_caveats", "retry_extraction", "human_review"]},
        "fields_to_fix": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    })

    def __init__(self, model=None, api_key=None, callbacks=None,
                 prompt_version: str = "arbiter_docclass_pilot_v0"):
        super().__init__(model=model, api_key=api_key,
                         prompt_version=prompt_version, callbacks=callbacks)


class ReporterAgent(_StructuredAgent):
    agent_name = "reporter"

    REPORTER_SCHEMA = build_structured_schema({
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    })

    def __init__(self, model=None, api_key=None, callbacks=None,
                 prompt_version: str = "reporter"):
        super().__init__(model=model, api_key=api_key,
                         prompt_version=prompt_version, callbacks=callbacks)


class PdfTranscriberAgent(_StructuredAgent):
    agent_name = "pdf_transcriber"

    TRANSCRIBER_SCHEMA = build_structured_schema({
        "markdown": {"type": "string"},
    })

    def __init__(self, model=None, api_key=None, callbacks=None,
                 prompt_version: str = "pdf_transcriber"):
        super().__init__(model=model, api_key=api_key,
                         prompt_version=prompt_version, callbacks=callbacks)
