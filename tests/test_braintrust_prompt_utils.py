"""Unit tests for Braintrust prompt registry helpers."""

from src.braintrust_utils import completion_prompt_content, get_prompt_by_slug


def test_completion_prompt_content_extracts_text():
    obj = {
        "prompt_data": {
            "prompt": {"type": "completion", "content": "Classify {{text}}"},
        },
    }
    assert completion_prompt_content(obj) == "Classify {{text}}"


def test_completion_prompt_content_none_for_chat():
    obj = {"prompt_data": {"prompt": {"type": "chat", "messages": []}}}
    assert completion_prompt_content(obj) is None


def test_get_prompt_by_slug_parses_list(monkeypatch):
    import src.braintrust_utils as bu

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"objects": [{"slug": "sorter_v0", "prompt_data": {}}]}

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(bu.requests, "get", lambda *a, **k: FakeResp())
    result = get_prompt_by_slug("sk", "proj", "sorter_v0")
    assert result["slug"] == "sorter_v0"
