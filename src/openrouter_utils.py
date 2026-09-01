"""Shared OpenRouter constants and request helpers.

The API base is overridable via the ``OPENROUTER_BASE_URL`` environment
variable so any OpenAI-compatible vision endpoint can be plugged in without
code changes: OpenRouter (default), a local Ollama server, or a self-hosted vLLM server.
"""

import os

# KANBAN-096: the URL is now resolved AT CLIENT-BUILD TIME, not import time.
# Import-time binding meant setting OPENROUTER_BASE_URL via dotenv (loaded
# lazily by src.env_utils at client construction) never took effect — only
# real shell exports worked, which silently broke the Modal-vLLM flip story.
# The resolver functions below are the seam every consumer must use.
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Deprecated frozen snapshots (kept for backward compatibility with any
# external importer); in-repo consumers use resolve_*() instead.
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL
).rstrip("/")
OPENROUTER_API_URL = os.environ.get(
    "OPENROUTER_API_URL", f"{OPENROUTER_BASE_URL}/chat/completions"
)


def resolve_openrouter_base_url() -> str:
    """Return the OpenAI-compatible API base, honoring ``OPENROUTER_BASE_URL``.

    Read at call time so dotenv-loaded configuration (``src.env_utils.load_env``
    runs lazily right before client construction) and test monkeypatches both
    take effect. This is the entity pipeline's provider seam: point it at
    OpenRouter (default), a local Ollama server, or a Modal-hosted vLLM
    deployment without code changes.
    """
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).rstrip(
        "/"
    )


def resolve_openrouter_api_url() -> str:
    """Return the chat-completions endpoint, resolved at call time.

    ``OPENROUTER_API_URL`` overrides wholesale when set; otherwise the
    standard ``{base}/chat/completions`` shape is composed from
    :func:`resolve_openrouter_base_url`.
    """
    override = os.environ.get("OPENROUTER_API_URL")
    if override:
        return override
    return f"{resolve_openrouter_base_url()}/chat/completions"

OUTPUT_FORMAT_MARKER = "## Output format"


def split_prompt(prompt: str) -> tuple[str, str]:
    """Split a classification prompt into (system_text, user_text).

    system_text is the instruction context up to (and excluding) the first
    ``## Output format`` header; user_text is the remainder (the output
    format contract, plus any trailing calibration/work-example text).
    """
    if not prompt:
        return "", ""
    idx = prompt.find(OUTPUT_FORMAT_MARKER)
    if idx == -1:
        return prompt, ""
    system_text = prompt[:idx]
    user_text = prompt[idx:]
    return system_text, user_text


def build_vision_messages(
    prompt: str,
    image_base64: str,
    image_format: str = "png",
    split_intro: bool = False,
) -> list[dict]:
    """Build an OpenAI-style ``messages`` payload with a text prompt and image."""
    if split_intro:
        system_text, user_text = split_prompt(prompt)
        messages = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        user_content: list[dict] = []
        if user_text:
            user_content.append({"type": "text", "text": user_text})
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/{image_format};base64,{image_base64}"
            },
        })
        messages.append({"role": "user", "content": user_content})
        return messages

    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{image_format};base64,{image_base64}"
                    },
                },
            ],
        }
    ]


def build_text_messages(system_prompt: str, user_text: str) -> list[dict]:
    """Build a standard text-only messages payload for classification/extraction tasks."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
