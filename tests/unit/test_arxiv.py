import json
from types import SimpleNamespace

import pytest
import httpx

from data import arxiv_client



# вспомогательные функции для создания тестовых данных и моков

def make_entry(
    *,
    entry_id="http://arxiv.org/abs/2401.12345v2",
    title="Test title",
    summary="Test abstract",
    authors=None,
    published_parsed=(2024, 1, 15, 12, 30, 45, 0, 0, 0),
    primary_term="cs.AI",
    tags=None,
):
    """Собрать объект, похожий на feedparser entry."""
    if authors is None:
        authors = [SimpleNamespace(name="Alice"), SimpleNamespace(name="Bob")]

    if tags is None:
        tags = [{"term": "cs.AI"}, {"term": "cs.LG"}]

    entry = SimpleNamespace(
        id=entry_id,
        title=title,
        summary=summary,
        authors=authors,
        published_parsed=published_parsed,
        tags=tags,
        arxiv_primary_category={"term": primary_term},
    )
    return entry


class DummyResponse:
    """Простой мок httpx.Response-подобного объекта."""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://export.arxiv.org/api/query")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP error {self.status_code}",
                request=request,
                response=response,
            )



# _parse_arxiv_id

def test_parse_arxiv_id_removes_version():
    result = arxiv_client._parse_arxiv_id("https://arxiv.org/abs/2401.12345v2")
    assert result == "2401.12345"


def test_parse_arxiv_id_without_version():
    result = arxiv_client._parse_arxiv_id("https://arxiv.org/abs/2401.12345")
    assert result == "2401.12345"


def test_parse_arxiv_id_keeps_tail_if_not_abs_url():
    result = arxiv_client._parse_arxiv_id("2401.12345v3")
    assert result == "2401.12345"



# _parse_authors

def test_parse_authors_returns_json_string():
    entry = SimpleNamespace(
        authors=[SimpleNamespace(name="Alice"), SimpleNamespace(name="Bob")]
    )
    result = arxiv_client._parse_authors(entry)

    assert isinstance(result, str)
    assert json.loads(result) == ["Alice", "Bob"]


def test_parse_authors_ignores_items_without_name():
    entry = SimpleNamespace(
        authors=[SimpleNamespace(name="Alice"), SimpleNamespace(other="NoName")]
    )
    result = arxiv_client._parse_authors(entry)

    assert json.loads(result) == ["Alice"]


def test_parse_authors_returns_empty_json_if_authors_missing():
    entry = SimpleNamespace()
    result = arxiv_client._parse_authors(entry)

    assert result == "[]"



# _parse_entry

def test_parse_entry_success_full_data():
    entry = make_entry()

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["arxiv_id"] == "2401.12345"
    assert result["title"] == "Test title"
    assert result["abstract"] == "Test abstract"
    assert json.loads(result["authors"]) == ["Alice", "Bob"]
    assert result["published_at"].year == 2024
    assert result["published_at"].month == 1
    assert result["published_at"].day == 15
    assert result["url"] == "https://arxiv.org/abs/2401.12345"
    assert result["primary_category"] == "cs.AI"
    assert json.loads(result["subjects"]) == ["cs.AI", "cs.LG"]


def test_parse_entry_strips_spaces_and_replaces_newlines():
    entry = make_entry(
        title="   My\nTitle   ",
        summary="   Some\nabstract text   ",
    )

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["title"] == "My Title"
    assert result["abstract"] == "Some abstract text"


@pytest.mark.parametrize(
    "field_name, kwargs",
    [
        ("id", {"entry_id": None}),
        ("title", {"title": None}),
        ("summary", {"summary": None}),
    ],
)
def test_parse_entry_returns_none_when_required_field_missing(field_name, kwargs):
    entry = make_entry(**kwargs)

    result = arxiv_client._parse_entry(entry)

    assert result is None


def test_parse_entry_returns_none_and_logs_warning_when_required_field_missing(caplog):
    entry = make_entry(entry_id=None)

    with caplog.at_level("WARNING"):
        result = arxiv_client._parse_entry(entry)

    assert result is None
    assert "Пропускаем запись без обязательных полей" in caplog.text


def test_parse_entry_handles_missing_primary_category():
    entry = make_entry()
    del entry.arxiv_primary_category

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["primary_category"] is None


def test_parse_entry_handles_missing_tags():
    entry = make_entry()
    entry.tags = []

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["subjects"] is None


def test_parse_entry_ignores_tags_without_term():
    entry = make_entry(tags=[{"term": "cs.AI"}, {"foo": "bar"}, {"term": "cs.CL"}])

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert json.loads(result["subjects"]) == ["cs.AI", "cs.CL"]


def test_parse_entry_handles_missing_published_parsed():
    entry = make_entry()
    entry.published_parsed = None

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["published_at"] is None


def test_parse_entry_handles_invalid_published_parsed_type_error():
    entry = make_entry(published_parsed="not-a-valid-date")

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["published_at"] is None


def test_parse_entry_handles_invalid_published_parsed_value_error():
    entry = make_entry(published_parsed=(2024, 13, 99, 99, 99, 99))

    result = arxiv_client._parse_entry(entry)

    assert result is not None
    assert result["published_at"] is None



# ТЕСТЫ ДЛЯ search

@pytest.mark.asyncio
async def test_search_success(monkeypatch):
    parsed_entries = [
        make_entry(entry_id="http://arxiv.org/abs/2401.00001v1", title="Paper 1"),
        make_entry(entry_id="http://arxiv.org/abs/2401.00002v2", title="Paper 2"),
    ]

    captured = {
        "requested_url": None,
        "sleep_called_with": None,
    }

    class DummyAsyncClient:
        def __init__(self, timeout):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            captured["requested_url"] = url
            return DummyResponse("<feed>fake</feed>", status_code=200)

    def fake_feedparser_parse(text):
        assert text == "<feed>fake</feed>"
        return SimpleNamespace(entries=parsed_entries)

    async def fake_sleep(delay):
        captured["sleep_called_with"] = delay

    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(arxiv_client.feedparser, "parse", fake_feedparser_parse)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    results = await arxiv_client.search("cat:cs.AI", max_results=2, start=5)

    assert len(results) == 2
    assert results[0]["arxiv_id"] == "2401.00001"
    assert results[1]["arxiv_id"] == "2401.00002"
    assert "search_query=cat%3Acs.AI" in captured["requested_url"]
    assert "start=5" in captured["requested_url"]
    assert "max_results=2" in captured["requested_url"]
    assert "sortBy=submittedDate" in captured["requested_url"]
    assert "sortOrder=descending" in captured["requested_url"]
    assert captured["sleep_called_with"] == arxiv_client._REQUEST_DELAY


@pytest.mark.asyncio
async def test_search_uses_settings_default_when_max_results_is_none(monkeypatch):
    parsed_entries = [make_entry()]

    class DummyAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            assert "max_results=7" in url
            return DummyResponse("<feed>fake</feed>", status_code=200)

    def fake_feedparser_parse(text):
        return SimpleNamespace(entries=parsed_entries)

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client.settings, "arxiv_max_results", 7)
    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(arxiv_client.feedparser, "parse", fake_feedparser_parse)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    results = await arxiv_client.search("cat:cs.AI", max_results=None)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_filters_out_entries_that_parse_to_none(monkeypatch):
    bad_entry = make_entry(entry_id=None)
    good_entry = make_entry(entry_id="http://arxiv.org/abs/2401.99999v1")

    class DummyAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse("<feed>fake</feed>", status_code=200)

    def fake_feedparser_parse(text):
        return SimpleNamespace(entries=[bad_entry, good_entry])

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(arxiv_client.feedparser, "parse", fake_feedparser_parse)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    results = await arxiv_client.search("cat:cs.AI", max_results=2)

    assert len(results) == 1
    assert results[0]["arxiv_id"] == "2401.99999"


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_feed_has_no_entries(monkeypatch):
    class DummyAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse("<feed>empty</feed>", status_code=200)

    def fake_feedparser_parse(text):
        return SimpleNamespace(entries=[])

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(arxiv_client.feedparser, "parse", fake_feedparser_parse)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    results = await arxiv_client.search("cat:cs.AI", max_results=5)

    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_http_error(monkeypatch):
    class DummyAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse("error", status_code=500)

    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)

    with pytest.raises(httpx.HTTPStatusError):
        await arxiv_client.search("cat:cs.AI", max_results=3)


@pytest.mark.asyncio
async def test_search_logs_messages(monkeypatch, caplog):
    class DummyAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse("<feed>fake</feed>", status_code=200)

    def fake_feedparser_parse(text):
        return SimpleNamespace(entries=[make_entry()])

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client.httpx, "AsyncClient", DummyAsyncClient)
    monkeypatch.setattr(arxiv_client.feedparser, "parse", fake_feedparser_parse)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    with caplog.at_level("INFO"):
        results = await arxiv_client.search("cat:cs.AI", max_results=1, start=0)

    assert len(results) == 1
    assert "arXiv API запрос" in caplog.text
    assert "arXiv вернул 1 статей" in caplog.text



# search_by_categories

@pytest.mark.asyncio
async def test_search_by_categories_builds_or_query(monkeypatch):
    captured = {"query": None, "max_results": None}

    async def fake_search(query, max_results=None, start=0):
        captured["query"] = query
        captured["max_results"] = max_results
        return [{"arxiv_id": "1"}]

    monkeypatch.setattr(arxiv_client, "search", fake_search)

    results = await arxiv_client.search_by_categories(
        ["cs.AI", "cs.LG", "cs.CL"],
        max_results=15,
    )

    assert results == [{"arxiv_id": "1"}]
    assert captured["query"] == "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
    assert captured["max_results"] == 15


@pytest.mark.asyncio
async def test_search_by_categories_with_single_category(monkeypatch):
    captured = {"query": None}

    async def fake_search(query, max_results=None, start=0):
        captured["query"] = query
        return []

    monkeypatch.setattr(arxiv_client, "search", fake_search)

    results = await arxiv_client.search_by_categories(["cs.AI"], max_results=5)

    assert results == []
    assert captured["query"] == "cat:cs.AI"


@pytest.mark.asyncio
async def test_search_by_categories_with_empty_list(monkeypatch):
    captured = {"query": None}

    async def fake_search(query, max_results=None, start=0):
        captured["query"] = query
        return []

    monkeypatch.setattr(arxiv_client, "search", fake_search)

    results = await arxiv_client.search_by_categories([], max_results=5)

    assert results == []
    assert captured["query"] == ""



# fetch_batch

@pytest.mark.asyncio
async def test_fetch_batch_collects_multiple_batches(monkeypatch):
    calls = []

    async def fake_search(query, max_results=None, start=0):
        calls.append({
            "query": query,
            "max_results": max_results,
            "start": start,
        })

        if start == 0:
            return [{"arxiv_id": "1"}, {"arxiv_id": "2"}]
        if start == 2:
            return [{"arxiv_id": "3"}, {"arxiv_id": "4"}]
        if start == 4:
            return [{"arxiv_id": "5"}]
        return []

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client, "search", fake_search)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    results = await arxiv_client.fetch_batch(
        query="cat:cs.AI",
        total=5,
        batch_size=2,
    )

    assert results == [
        {"arxiv_id": "1"},
        {"arxiv_id": "2"},
        {"arxiv_id": "3"},
        {"arxiv_id": "4"},
        {"arxiv_id": "5"},
    ]
    assert calls == [
        {"query": "cat:cs.AI", "max_results": 2, "start": 0},
        {"query": "cat:cs.AI", "max_results": 2, "start": 2},
        {"query": "cat:cs.AI", "max_results": 1, "start": 4},
    ]


@pytest.mark.asyncio
async def test_fetch_batch_stops_on_empty_batch(monkeypatch, caplog):
    calls = []

    async def fake_search(query, max_results=None, start=0):
        calls.append((query, max_results, start))
        if start == 0:
            return [{"arxiv_id": "1"}, {"arxiv_id": "2"}]
        return []

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client, "search", fake_search)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    with caplog.at_level("INFO"):
        results = await arxiv_client.fetch_batch(
            query="cat:cs.AI",
            total=10,
            batch_size=2,
        )

    assert results == [{"arxiv_id": "1"}, {"arxiv_id": "2"}]
    assert calls == [
        ("cat:cs.AI", 2, 0),
        ("cat:cs.AI", 2, 2),
    ]
    assert "arXiv вернул пустой батч — останавливаем загрузку" in caplog.text


@pytest.mark.asyncio
async def test_fetch_batch_with_total_zero(monkeypatch):
    called = {"search_called": False}

    async def fake_search(query, max_results=None, start=0):
        called["search_called"] = True
        return []

    monkeypatch.setattr(arxiv_client, "search", fake_search)

    results = await arxiv_client.fetch_batch(
        query="cat:cs.AI",
        total=0,
        batch_size=100,
    )

    assert results == []
    assert called["search_called"] is False


@pytest.mark.asyncio
async def test_fetch_batch_logs_progress(monkeypatch, caplog):
    async def fake_search(query, max_results=None, start=0):
        if start == 0:
            return [{"arxiv_id": "1"}, {"arxiv_id": "2"}]
        if start == 2:
            return [{"arxiv_id": "3"}]
        return []

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr(arxiv_client, "search", fake_search)
    monkeypatch.setattr(arxiv_client.asyncio, "sleep", fake_sleep)

    with caplog.at_level("INFO"):
        results = await arxiv_client.fetch_batch(
            query="cat:cs.AI",
            total=3,
            batch_size=2,
        )

    assert len(results) == 3
    assert "Загружено 2 / 3 статей" in caplog.text
    assert "Загружено 3 / 3 статей" in caplog.text