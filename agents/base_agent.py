"""Base agent class — LangChain-powered LLM helpers with structured output.

Every mailroom agent is a small LangChain Runnable wrapper: a ``ChatOpenAI``
instance pointed at OpenRouter (or any OpenAI-compatible endpoint via
``OPENROUTER_BASE_URL``) composed with prompt templates and optional JSON
schema parsing.

Design notes
------------
- Prompts are loaded by version from ``src.prompts`` so the evaluation loops
  can test exactly ONE prompt version per Braintrust experiment.
- Structured calls use ``with_structured_output`` (JSON schema) so specialists
  and the sorter emit strict JSON that Braintrust scorers can rely on.
- All calls are traced to Braintrust via ``braintrust.integrations.langchain``
  when the eval runners call ``setup_langchain`` first (they always do).
"""

from __future__ import annotations

import json
import os
import structlog
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.openrouter_utils import resolve_openrouter_base_url

logger = structlog.get_logger(__name__)


def build_structured_schema(
    properties: dict,
    required: list[str] | None = None,
    additional_properties: bool = False,
    title: str = "StructuredOutput",
) -> dict:
    """Build a JSON schema dict for structured output.

    ``title`` is required by LangChain's ``with_structured_output`` (it is used
    as the function/tool name on OpenAI-compatible endpoints).
    """
    return {
        "type": "object",
        "title": title,
        "properties": properties,
        "required": required or list(properties.keys()),
        "additionalProperties": additional_properties,
    }


class BaseAgent(ABC):
    """Abstract base class for all mailroom agents (LangChain runnables)."""

    agent_name: str

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        callbacks: list | None = None,
    ):
        self.model = model or "qwen/qwen3.7-flash"
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        # Optional LangChain callback handlers (e.g. the Langfuse
        # CallbackHandler) attached to every invoke; None keeps the default
        # (Braintrust setup_langchain) tracing path unchanged.
        self._callbacks = list(callbacks) if callbacks else None
        self._max_tokens = 4096
        self._max_input_chars = 100_000  # full-document budget; only a hard safety cap
        self._temperature = 0.1
        self._reasoning_effort = None
        self._llm: ChatOpenAI | None = None
        self._last_usage: dict | None = None
        self._last_truncated = False

    @abstractmethod
    def system_prompt(self) -> str:
        """Return the agent's system prompt string."""
        ...

    # ------------------------------------------------------------------
    # LangChain plumbing
    # ------------------------------------------------------------------

    def llm(self) -> ChatOpenAI:
        """Lazily build the LangChain ``ChatOpenAI`` client.

        Uses the OpenAI-compatible provider seam so any endpoint —
        OpenRouter (default), Ollama, or a Modal-hosted vLLM deployment
        (KANBAN-096) — can be swapped in via ``OPENROUTER_BASE_URL``.
        Resolved at call time (after ``load_env()``), so dotenv-set values
        take effect; see ``src/openrouter_utils.py::resolve_openrouter_base_url``.
        """
        if self._llm is None:
            from src.env_utils import load_env

            load_env()
            self._llm = ChatOpenAI(
                model=self.model,
                api_key=self.api_key or os.environ.get("OPENROUTER_API_KEY") or None,
                base_url=resolve_openrouter_base_url(),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout=120,
                max_retries=3,
            )
            if self._reasoning_effort:
                self._llm.extra_body = {"reasoning": {"effort": self._reasoning_effort}}
        return self._llm

    # Share of the input budget kept from the document's TAIL when truncation
    # fires: deal-critical sections (term, termination, renewal, governing law,
    # signatures) sit in the closing portion of long agreements, which a
    # head-only cap loses entirely — the 292k-char Phasebio agreement's
    # governing-law clause at char 276k is invisible under a 100k head cap.
    TRUNCATION_TAIL_FRACTION = 0.4

    def truncate_input(self, text: str) -> str:
        """Return the FULL document text, capping only past the hard budget.

        The sorter is meant to classify the full document (fully extracted
        markdown text, not a 50-token preview). ``_max_input_chars`` is a
        safety cap for pathological documents only; when it fires, the input
        is kept as a HEAD + TAIL window instead of the head alone: the first
        ``(1 - TRUNCATION_TAIL_FRACTION)`` of the budget from the opening
        (recitals, parties, definitions, early obligations) plus the remaining
        share from the CLOSING portion (term, termination, renewal, governing
        law, signature pages). A marker between the two records the truncation
        on ``_last_truncated`` so callers (and the eval loop's span metadata)
        can see that the row saw partial input.
        """
        if len(text) <= self._max_input_chars:
            self._last_truncated = False
            return text
        self._last_truncated = True
        logger.warning(
            "input_truncated",
            agent=self.agent_name,
            chars=len(text),
            cap=self._max_input_chars,
            tail_fraction=self.TRUNCATION_TAIL_FRACTION,
        )
        budget = max(1, int(self._max_input_chars))
        head = int(budget * (1.0 - self.TRUNCATION_TAIL_FRACTION))
        return (
            text[:head]
            + f"\n\n[... document truncated, {len(text)} total chars; middle omitted — "
              f"closing portion continues below (term, termination, governing law) ...]\n\n"
            + text[-(budget - head):]
        )

    # ------------------------------------------------------------------
    # Completion helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        user_message: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        """Plain text completion via the LangChain chain.

        Args:
            user_message: The user-facing message content.
            system_prompt: System prompt (defaults to self.system_prompt()).
            temperature: Sampling temperature (defaults to self._temperature).
            max_tokens: Max output tokens (defaults to self._max_tokens).
            reasoning_effort: Reasoning effort level for Qwen models.

        Returns:
            The model's response text.
        """
        llm = self.llm()
        if temperature is not None or max_tokens is not None:
            llm = llm.bind(
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
        if reasoning_effort:
            llm = llm.bind(extra_body={"reasoning": {"effort": reasoning_effort}})

        system = system_prompt or self.system_prompt()
        # System prompts are literal text (they may legally contain curly
        # braces, e.g. embedded JSON schemas) — never template-parsed.
        prompt = ChatPromptTemplate.from_messages(
            [SystemMessage(content=system), ("human", "{text}")]
        )
        chain = prompt | llm

        logger.info("llm_call", agent=self.agent_name, model=self.model)
        raw: Any = chain.invoke(
            {"text": user_message},
            config={"callbacks": self._callbacks} if self._callbacks else None,
        )

        # Capture usage/cost from the raw AIMessage (same accounting as the
        # structured + vision paths) so plain-text completions — e.g. the
        # LegalBench task-mode answers — carry token/cost records too.
        usage = getattr(raw, "usage_metadata", None) or (raw.response_metadata or {}).get("usage") or {}
        self._last_usage = {
            "prompt_tokens": usage.get("input_tokens") or usage.get("prompt_tokens") or 0,
            "completion_tokens": usage.get("output_tokens") or usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "cost": (raw.response_metadata or {}).get("cost"),
        }
        if isinstance(raw.content, str):
            content = raw.content
        elif isinstance(raw.content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw.content
            )
        else:
            content = str(raw.content or "")
        logger.info("llm_response", agent=self.agent_name, length=len(content))
        return content

    def _call_structured(
        self,
        user_message: str,
        json_schema: dict,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Structured JSON extraction via ``with_structured_output``.

        Args:
            user_message: User message containing the document text.
            json_schema: JSON schema dict describing expected output structure.
            system_prompt: Override system prompt.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.

        Returns:
            Parsed JSON dict, or {"_raw": raw_text, "_parse_error": True} on failure.
        """
        llm = self.llm()
        if temperature is not None or max_tokens is not None:
            llm = llm.bind(
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
        try:
            structured = llm.with_structured_output(
                json_schema, method="json_schema", include_raw=True
            )
        except Exception:  # pragma: no cover - older SDKs fall back to prompting
            structured = llm.with_structured_output(json_schema, method="function_calling", include_raw=True)

        system = system_prompt or self.system_prompt()
        # Literal SystemMessage: system prompts may contain curly braces
        # (embedded JSON schemas) and must not be template-parsed.
        prompt = ChatPromptTemplate.from_messages(
            [SystemMessage(content=system), ("human", "{text}")]
        )
        chain = prompt | structured

        logger.info("llm_structured_call", agent=self.agent_name, model=self.model)
        raw_out: Any = chain.invoke(
            {"text": user_message},
            config={"callbacks": self._callbacks} if self._callbacks else None,
        )

        # include_raw=True returns {"raw": AIMessage, "parsed": ..., "parsing_error": ...}
        if isinstance(raw_out, dict):
            message = raw_out.get("raw")
            result = raw_out.get("parsed")
            parsing_error = raw_out.get("parsing_error")
        else:
            message = getattr(raw_out, "raw", None)
            result = getattr(raw_out, "parsed", None)
            parsing_error = getattr(raw_out, "parsing_error", None)

        # Capture usage/cost from the raw AIMessage for the Braintrust cost scorer.
        if message is not None:
            usage = getattr(message, "usage_metadata", None) or (message.response_metadata or {}).get("usage") or {}
            self._last_usage = {
                "prompt_tokens": usage.get("input_tokens") or usage.get("prompt_tokens") or 0,
                "completion_tokens": usage.get("output_tokens") or usage.get("completion_tokens") or 0,
                "total_tokens": usage.get("total_tokens") or 0,
                "cost": (message.response_metadata or {}).get("cost"),
            }
        else:
            self._last_usage = None

        if result is None and parsing_error is not None:
            logger.error("structured_output_parse_error", agent=self.agent_name, error=str(parsing_error))
            raw_text = ""
            if message is not None:
                raw_text = message.content if isinstance(message.content, str) else ""
            return {"_raw": raw_text, "_parse_error": True}

        if not isinstance(result, dict):
            try:
                result = result.model_dump()
            except AttributeError:
                logger.error("structured_output_unparseable", agent=self.agent_name)
                return {"_raw": str(result), "_parse_error": True}

        logger.info("llm_structured_response", agent=self.agent_name, keys=list(result.keys()))
        return result

    def _call_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_base64: str,
        image_format: str = "png",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Vision classification call: system prompt + user text + ONE image.

        The image is sent as an inline data URI (``data:image/png;base64,...``)
        in a multimodal LangChain message — the same payload shape the
        RVL-CDIP classifier uses, but through the LangChain stack so the call
        is traced to Braintrust like every other agent call.

        Args:
            system_prompt: The classification rules (e.g. the intro half of the
                vision prompt, split at ``## Output format``).
            user_text: The output-format contract + any worked examples.
            image_base64: The document page image, base64-encoded.
            image_format: Image MIME format ('png', 'jpeg').
            temperature: Sampling temperature.
            max_tokens: Max output tokens.

        Returns:
            The model's raw response text.
        """
        return self._call_vision_multi(
            system_prompt=system_prompt,
            user_text=user_text,
            images=[(image_base64, image_format)],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _call_vision_multi(
        self,
        system_prompt: str,
        user_text: str,
        images: list[tuple[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Vision classification call with MULTIPLE page images in ONE request.

        The FULL document (every rendered page) is sent in a single call so the
        model sees the entire PDF at once — one classification per PDF, not one
        per page. ``images`` is a list of ``(base64, format)`` tuples, each
        attached as an inline data URI.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = self.llm()
        if temperature is not None or max_tokens is not None:
            llm = llm.bind(
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._max_tokens,
            )

        content: list[dict] = [{"type": "text", "text": user_text}]
        for base64_image, image_format in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{image_format};base64,{base64_image}"},
            })

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]

        logger.info("llm_vision_call", agent=self.agent_name, model=self.model, pages=len(images))
        response = llm.invoke(
            messages,
            config={"callbacks": self._callbacks} if self._callbacks else None,
        )
        raw_content = response.content if isinstance(response.content, str) else str(response.content)

        usage = getattr(response, "usage_metadata", None) or (response.response_metadata or {}).get("usage") or {}
        self._last_usage = {
            "prompt_tokens": usage.get("input_tokens") or usage.get("prompt_tokens") or 0,
            "completion_tokens": usage.get("output_tokens") or usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "cost": (response.response_metadata or {}).get("cost"),
        }
        logger.info("llm_vision_response", agent=self.agent_name, length=len(raw_content))
        return raw_content
