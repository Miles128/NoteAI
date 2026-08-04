from types import SimpleNamespace

from sidecar.rag import web_search


def test_web_search_prefers_bing(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        web_search, "bing_search", lambda query: calls.append(("bing", query)) or [{"url": "https://example.com"}]
    )
    monkeypatch.setattr(web_search, "duckduckgo_search", lambda _query: calls.append(("ddg", "")) or [])

    result = web_search.web_search("NoteAI")

    assert result == [{"url": "https://example.com"}]
    assert calls == [("bing", "NoteAI")]


def test_bing_search_extracts_results(monkeypatch) -> None:
    html = '<li class="b_algo"><h2><a href="https://example.com">Example</a></h2><div class="b_caption"><p>Snippet</p></div></li>'
    response = SimpleNamespace(text=html, url="https://www.bing.com/search?q=test", raise_for_status=lambda: None)
    monkeypatch.setattr(web_search.requests, "get", lambda *_args, **_kwargs: response)

    assert web_search.bing_search("test") == [{"title": "Example", "url": "https://example.com", "snippet": "Snippet"}]


def test_string_attribute_rejects_list_values() -> None:
    assert web_search._string_attribute(["https://example.com", "unexpected"]) == ""
    assert web_search._string_attribute(" https://example.com ") == "https://example.com"
