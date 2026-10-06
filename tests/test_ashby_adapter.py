from unittest.mock import Mock

import pytest
import requests

from career_radar.ingestion.ashby_adapter import AshbyAdapter, AshbyError


def job(**changes):
    return {
        "id": "job-1",
        "title": "Data Engineer",
        "jobUrl": "https://jobs.ashbyhq.com/example/job-1",
        "location": "Remote U.S.",
        "isRemote": None,
        "isListed": True,
        "publishedAt": "2026-10-06T12:00:00Z",
        "descriptionPlain": "Example description",
        **changes,
    }


def adapter_for(payload):
    session = Mock(spec=requests.Session)
    session.get.return_value.json.return_value = payload
    return AshbyAdapter(session=session), session


def test_documented_mapping_and_request():
    adapter, session = adapter_for({"jobs": [job()]})
    board = adapter.fetch_board("example")
    posting = board.postings[0]
    assert (board.source, board.board_slug) == ("ashby", "example")
    assert posting.title == "Data Engineer"
    assert posting.external_id == "job-1"
    assert posting.is_remote is True
    assert posting.country_code == "US"
    assert posting.updated_at is None  # Publication is not an update timestamp.
    assert posting.content == "Example description"
    session.get.assert_called_once_with(
        "https://api.ashbyhq.com/posting-api/job-board/example", timeout=(5.0, 20.0)
    )


def test_provider_flag_and_url_identity_fallback():
    raw = job(isRemote=True, location="São Paulo", descriptionHtml="<p>Example</p>")
    del raw["id"]
    adapter, _ = adapter_for({"jobs": [raw]})
    posting = adapter.fetch_board("example").postings[0]
    assert posting.external_id == str(posting.url)
    assert posting.is_remote is True
    assert posting.country_code == "BR"
    assert posting.content == "<p>Example</p>"


@pytest.mark.parametrize("payload", [None, [], {}, {"jobs": {}}, {"jobs": None}])
def test_bad_envelope(payload):
    adapter, _ = adapter_for(payload)
    with pytest.raises(AshbyError, match="missing jobs"):
        adapter.fetch_board("example")


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        {},
        job(title=None),
        job(jobUrl="bad"),
        job(isRemote="false"),
        job(id=""),
        job(isListed="false"),
    ],
)
def test_one_invalid_record_fails_entire_board(invalid):
    adapter, _ = adapter_for({"jobs": [job(), invalid]})
    with pytest.raises(AshbyError, match="1 invalid record"):
        adapter.fetch_board("example")


def test_empty_and_unlisted():
    for jobs in ([], [job(isListed=False)]):
        adapter, _ = adapter_for({"jobs": jobs})
        assert adapter.fetch_board("example").postings == []


@pytest.mark.parametrize(
    "error",
    [requests.Timeout(), requests.ConnectionError(), ValueError("invalid json")],
)
def test_network_and_parse_errors(error):
    adapter, session = adapter_for({})
    session.get.side_effect = error
    with pytest.raises(AshbyError):
        adapter.fetch_board("example")


@pytest.mark.parametrize("status", [404, 429, 500])
def test_http_errors(status):
    adapter, session = adapter_for({})
    response = requests.Response()
    response.status_code = status
    session.get.return_value.raise_for_status.side_effect = requests.HTTPError(
        response=response
    )
    with pytest.raises(AshbyError, match=f"HTTP {status}"):
        adapter.fetch_board("example")


def test_invalid_slug_does_not_make_request():
    adapter, session = adapter_for({})
    with pytest.raises(AshbyError, match="slug"):
        adapter.fetch_board("../other?query=true")
    session.get.assert_not_called()
