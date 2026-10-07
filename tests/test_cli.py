from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from career_radar import cli
from career_radar.ingestion.ashby_adapter import AshbyError
from career_radar.ingestion.models import CompanyBoard
from career_radar.storage.repository import UpsertResult


@pytest.mark.parametrize(
    "source,slug", [("ashby", "constructor"), ("greenhouse", "clara")]
)
def test_cli_routes_source(monkeypatch, source, slug):
    ingest = Mock(return_value=0)
    monkeypatch.setattr(cli, "run_ingest", ingest)
    monkeypatch.setattr(
        "sys.argv", ["career-radar", "--action", "ingest", "--source", source]
    )
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    ingest.assert_called_once_with(slug, 5, source)


def test_adapter_failure_never_touches_storage(monkeypatch):
    adapter = Mock()
    adapter.fetch_board.side_effect = AshbyError("invalid payload")
    engine = Mock()
    monkeypatch.setattr(cli, "AshbyAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(cli, "get_engine", engine)
    assert cli.run_ingest("example", 1, "ashby") == 1
    engine.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_storage_result_or_sanitized_failure(monkeypatch, capsys, fail):
    adapter = Mock()
    adapter.fetch_board.return_value = CompanyBoard(
        source="ashby", board_slug="example"
    )
    repository = Mock()
    repository.upsert_postings.return_value = UpsertResult(0, 0)
    if fail:
        repository.upsert_postings.side_effect = SQLAlchemyError("private detail")
    monkeypatch.setattr(cli, "AshbyAdapter", Mock(return_value=adapter))
    monkeypatch.setattr(cli, "get_engine", Mock())
    monkeypatch.setattr(cli, "JobPostingRepository", Mock(return_value=repository))
    assert cli.run_ingest("example", 1, "ashby") == int(fail)
    captured = capsys.readouterr()
    assert "private detail" not in captured.err
    if not fail:
        assert "Stored: 0 new, 0 updated" in captured.out


def test_cli_routes_classify(monkeypatch):
    classify = Mock(return_value=0)
    monkeypatch.setattr(cli, "run_classify", classify)
    monkeypatch.setattr("sys.argv", ["career-radar", "--action", "classify"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    classify.assert_called_once_with()


def test_run_classify_reports_count(monkeypatch, capsys):
    repository = Mock()
    repository.classify_unclassified.return_value = 7
    monkeypatch.setattr(cli, "get_engine", Mock())
    monkeypatch.setattr(cli, "JobPostingRepository", Mock(return_value=repository))
    assert cli.run_classify() == 0
    assert "Classified: 7 postings" in capsys.readouterr().out


def test_run_classify_hides_storage_details(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_engine", Mock(side_effect=SQLAlchemyError("pw")))
    assert cli.run_classify() == 1
    err = capsys.readouterr().err
    assert "SQLAlchemyError" in err and "pw" not in err
