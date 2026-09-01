"""LangChain chain factory for the prompt experiment loops.

Builds a fresh ``ChatPromptTemplate -> ChatOpenAI -> parser`` chain per
prompt version. Every evaluation tests exactly ONE prompt version: the chain
is constructed from ``src.prompts`` and stamped into the Braintrust
experiment metadata so experiments are comparable in the UI.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.openrouter_utils import resolve_openrouter_base_url
from src.prompts import get_prompt
from src.taxonomy import load_taxonomy

logger = structlog.get_logger(__name__)

# OpenRouter's structured-output path: OpenAI-compatible JSON mode via
# response_format on compatible models.
SUPPORTED_JSON_MODELS = ("qwen", "gpt", "deepseek", "gemini", "kimi", "moonshot")


def build_chat_model(
    model: str = "qwen/qwen3.7-flash",
    api_key: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
) -> ChatOpenAI:
    """Build a LangChain ``ChatOpenAI`` pointed at the provider seam.

    Defaults to OpenRouter; any OpenAI-compatible endpoint (Ollama, a
    Modal-hosted vLLM — KANBAN-096) can be swapped in via
    ``OPENROUTER_BASE_URL``, resolved at call time.
    """
    llm = ChatOpenAI(
        model=model,
        api_key=api_key or None,
        base_url=resolve_openrouter_base_url(),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120,
        max_retries=3,
    )
    if reasoning_effort:
        llm.extra_body = {"reasoning": {"effort": reasoning_effort}}
    return llm


def build_classification_chain(
    prompt_version: str = "sorter",
    model: str = "qwen/qwen3.7-flash",
    api_key: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    **extra: object,
) -> tuple:
    """Build the sorter chain for ``prompt_version``.

    The prompt is rendered via LangChain ``ChatPromptTemplate`` so ``{{var}}``
    placeholders are substituted, then parsed as JSON. Returns
    ``(chain, prompt_text)`` — the prompt text is stamped into experiment
    metadata so Braintrust records exactly what was tested.
    """
    prompt_text = get_prompt(prompt_version)
    # Literal SystemMessage: prompts may contain curly braces (embedded JSON)
    # and must not be template-parsed.
    template = ChatPromptTemplate.from_messages(
        [SystemMessage(content=prompt_text), ("human", "{document}")]
    )
    llm = build_chat_model(
        model=model, api_key=api_key, temperature=temperature, max_tokens=max_tokens
    )
    chain = template | llm | JsonOutputParser()
    return chain, prompt_text


def build_text_chain(
    system_prompt: str,
    model: str = "qwen/qwen3.7-flash",
    api_key: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> tuple:
    """Build a generic text chain with an explicit system prompt string.

    Used for judge chains (classification judge, correctness judge) where the
    prompt text is assembled per document. Returns ``(chain, prompt_text)``.
    """
    template = ChatPromptTemplate.from_messages(
        [SystemMessage(content=system_prompt), ("human", "{document}")]
    )
    llm = build_chat_model(
        model=model, api_key=api_key, temperature=temperature, max_tokens=max_tokens
    )
    chain = template | llm | StrOutputParser()
    return chain, system_prompt


def model_from_taxonomy(agent_name: str, default: str) -> str:
    """Resolve an agent's model from the taxonomy, falling back to ``default``."""
    taxonomy = load_taxonomy()
    return taxonomy.get("agents", {}).get(agent_name, {}).get("model", default)
