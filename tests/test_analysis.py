"""Analysis layer: Gemini contract, resume loading and evaluation loop (mocked)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from career_radar import cli
from career_radar.analysis import evaluator, llm_client
from career_radar.analysis.evaluator import (
    MAX_EVALUATIONS_PER_RUN,
    MAX_POSTING_CHARS,
    ResumeError,
    evaluate_pending,
    load_resume,
    posting_to_text,
)
from career_radar.analysis.llm_client import (
    EvaluationResponse,
    GeminiClient,
    LLMError,
    MatchEvaluation,
)
from career_radar.storage.repository import PendingPosting

VALID_JSON = '{"score": 7, "salary": "", "reason": "Strong SQL; no Airflow."}'


def pending(posting_id=1, content="<p>Build pipelines</p>"):
    return PendingPosting(
        id=posting_id,
        title="Data Engineer",
        location="Remote - Brazil",
        country_code="BR",
        url="https://example.com/job",
        content=content,
    )


def gemini(monkeypatch, text=VALID_JSON, error=None, model_version="gemini-x-001"):
    """GeminiClient whose SDK client is a Mock; returns (client, sdk_mock)."""
    sdk = Mock()
    if error is not None:
        sdk.models.generate_content.side_effect = error
    else:
        sdk.models.generate_content.return_value = SimpleNamespace(
            text=text, model_version=model_version
        )
    monkeypatch.setattr(llm_client.genai, "Client", Mock(return_value=sdk))
    return GeminiClient("test-key", "gemini-test"), sdk


def evaluation_response(score=8, salary="USD 5k/month"):
    return EvaluationResponse(
        MatchEvaluation(score=score, salary=salary, reason="Good fit."), "model-1"
    )


# --- Structured output contract -------------------------------------------


@pytest.mark.parametrize("score", [0, 11])
def test_score_outside_range_is_rejected(score):
    with pytest.raises(ValueError):
        MatchEvaluation(score=score, salary="", reason="x")


def test_blank_salary_becomes_null():
    evaluation = MatchEvaluation(score=5, salary="   ", reason=" ok ")
    assert evaluation.salary_or_none is None
    assert evaluation.reason == "ok"


def test_evaluate_forces_json_schema_and_returns_model_version(monkeypatch):
    client, sdk = gemini(monkeypatch)
    result = client.evaluate("resume text", "posting text")

    assert result.evaluation.score == 7
    assert result.evaluation.salary_or_none is None
    assert result.model == "gemini-x-001"
    kwargs = sdk.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    assert kwargs["model"] == "gemini-test"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == MatchEvaluation.model_json_schema()
    assert config.temperature == 0
    assert config.automatic_function_calling.disable is True
    assert "untrusted data" in config.system_instruction
    # Resume and posting are delimited so the posting cannot pose as instructions.
    assert (
        "<candidate_profile>\nresume text\n</candidate_profile>" in kwargs["contents"]
    )
    assert "<job_posting>\nposting text\n</job_posting>" in kwargs["contents"]


def test_missing_model_version_falls_back_to_requested_model(monkeypatch):
    client, _ = gemini(monkeypatch, model_version=None)
    assert client.evaluate("r", "p").model == "gemini-test"


@pytest.mark.parametrize(
    "text,message",
    [
        ("", "empty answer"),
        ("not json", "violates the schema"),
        ('{"score": 42, "salary": "", "reason": "x"}', "violates the schema"),
        ('{"score": 5, "reason": "missing salary"}', "violates the schema"),
    ],
)
def test_answer_outside_contract_raises(monkeypatch, text, message):
    client, _ = gemini(monkeypatch, text=text)
    with pytest.raises(LLMError, match=message):
        client.evaluate("r", "p")


def test_api_error_does_not_leak_message(monkeypatch):
    error = errors.ClientError(
        429, {"error": {"code": 429, "message": "secret detail", "status": "X"}}
    )
    client, _ = gemini(monkeypatch, error=error)
    with pytest.raises(LLMError) as raised:
        client.evaluate("r", "p")
    assert "429" in str(raised.value)
    assert "secret detail" not in str(raised.value)


def test_network_timeout_becomes_llm_error(monkeypatch):
    client, _ = gemini(monkeypatch, error=httpx.ReadTimeout("slow"))
    with pytest.raises(LLMError, match="ReadTimeout"):
        client.evaluate("r", "p")


def test_from_env_requires_key(monkeypatch):
    monkeypatch.setattr(llm_client, "load_dotenv", Mock())
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiClient.from_env()


def test_from_env_uses_model_override(monkeypatch):
    monkeypatch.setattr(llm_client, "load_dotenv", Mock())
    monkeypatch.setattr(llm_client.genai, "Client", Mock())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-other")
    assert GeminiClient.from_env().model == "gemini-other"
    monkeypatch.delenv("GEMINI_MODEL")
    assert GeminiClient.from_env().model == llm_client.DEFAULT_MODEL


# --- Resume input ----------------------------------------------------------


def test_load_resume_reads_external_markdown(tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("  # Candidate\nSQL, Python  \n", encoding="utf-8")
    assert load_resume(resume) == "# Candidate\nSQL, Python"


def test_load_resume_refuses_path_inside_repository():
    inside = Path(evaluator.__file__).resolve().parents[3] / "README.md"
    with pytest.raises(ResumeError, match="outside the repository"):
        load_resume(inside)


@pytest.mark.parametrize(
    "name,content,message",
    [
        ("resume.pdf", "x", ".md or .txt"),
        ("missing.md", None, "not found"),
        ("empty.txt", "   \n", "empty"),
        ("huge.md", "x" * (evaluator.MAX_RESUME_BYTES + 1), "larger than"),
    ],
    ids=["suffix", "missing", "empty", "too-large"],
)
def test_load_resume_rejects_invalid_files(tmp_path, name, content, message):
    path = tmp_path / name
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ResumeError, match=message):
        load_resume(path)


# --- Posting text ----------------------------------------------------------


def test_posting_text_unescapes_and_strips_html():
    content = "&lt;p&gt;Use &lt;strong&gt;SQL&lt;/strong&gt; &amp;amp; dbt&lt;/p&gt;"
    text = posting_to_text(pending(content=content))
    assert text.startswith("Title: Data Engineer\nLocation: Remote - Brazil")
    assert "Use SQL & dbt" in text
    assert "<" not in text


def test_posting_text_is_bounded():
    text = posting_to_text(pending(content="a" * (MAX_POSTING_CHARS * 2)))
    body = text.split("\n\n", 1)[1]
    assert body == "a" * MAX_POSTING_CHARS


# --- Evaluation loop -------------------------------------------------------


def test_evaluate_pending_stores_success_and_isolates_failure():
    repository = Mock()
    repository.fetch_unevaluated.return_value = [pending(1), pending(2)]
    repository.save_evaluation.return_value = True
    client = Mock()
    client.evaluate.side_effect = [evaluation_response(), LLMError("quota")]

    outcomes = evaluate_pending(repository, client, "resume", 2, ["BR"])

    repository.fetch_unevaluated.assert_called_once_with(2, ["BR"])
    assert [o.error for o in outcomes] == [None, "quota"]
    repository.save_evaluation.assert_called_once()
    args, kwargs = repository.save_evaluation.call_args
    assert args == (1,)
    assert kwargs["score"] == 8
    assert kwargs["salary"] == "USD 5k/month"
    assert kwargs["model"] == "model-1"
    assert kwargs["evaluated_at"].tzinfo is not None


def test_evaluate_pending_never_exceeds_hard_cap():
    repository = Mock()
    repository.fetch_unevaluated.return_value = []
    evaluate_pending(repository, Mock(), "resume", 10_000, ["BR"])
    repository.fetch_unevaluated.assert_called_once_with(
        MAX_EVALUATIONS_PER_RUN, ["BR"]
    )


def test_evaluate_pending_reports_vanished_row():
    repository = Mock()
    repository.fetch_unevaluated.return_value = [pending()]
    repository.save_evaluation.return_value = False
    client = Mock(evaluate=Mock(return_value=evaluation_response()))
    [outcome] = evaluate_pending(repository, client, "resume", 1, ["BR"])
    assert outcome.error == "posting no longer stored"


def test_evaluate_pending_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        evaluate_pending(Mock(), Mock(), "resume", 0, ["BR"])


# --- CLI -------------------------------------------------------------------


def test_cli_evaluate_requires_resume_path(monkeypatch):
    monkeypatch.setattr("sys.argv", ["career-radar", "--action", "evaluate"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 2


@pytest.mark.parametrize("flag", ["--resume-path", "--profile-path"])
def test_cli_routes_evaluate_arguments(monkeypatch, flag):
    run = Mock(return_value=0)
    monkeypatch.setattr(cli, "run_evaluate", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "career-radar",
            "--action",
            "evaluate",
            flag,
            "cv.md",
            "--limit",
            "2",
            "--allowed-countries",
            "br, pt",
        ],
    )
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    run.assert_called_once_with(Path("cv.md"), 2, ["BR", "PT"])


def test_run_evaluate_prints_results(monkeypatch, capsys, tmp_path):
    resume = tmp_path / "cv.md"
    resume.write_text("Candidate", encoding="utf-8")
    monkeypatch.setattr(cli.GeminiClient, "from_env", Mock())
    monkeypatch.setattr(cli, "get_engine", Mock())
    monkeypatch.setattr(cli, "JobPostingRepository", Mock())
    outcomes = [
        evaluator.EvaluationOutcome(pending(1), evaluation_response(salary="")),
        evaluator.EvaluationOutcome(pending(2), error="Gemini API error 429"),
    ]
    monkeypatch.setattr(cli, "evaluate_pending", Mock(return_value=outcomes))

    assert cli.run_evaluate(resume, 50, ["BR"]) == 1
    out = capsys.readouterr().out
    assert f"capped at {MAX_EVALUATIONS_PER_RUN}" in out
    assert "score: 8/10" in out
    assert "salary: not stated" in out
    assert "FAILED: Gemini API error 429" in out
    assert "Evaluated: 1 stored, 1 failed" in out


def test_run_evaluate_stops_before_any_call_without_key(monkeypatch, capsys, tmp_path):
    resume = tmp_path / "cv.md"
    resume.write_text("Candidate", encoding="utf-8")
    monkeypatch.setattr(
        cli.GeminiClient, "from_env", Mock(side_effect=LLMError("no key"))
    )
    engine = Mock()
    monkeypatch.setattr(cli, "get_engine", engine)
    assert cli.run_evaluate(resume, 1, ["BR"]) == 1
    assert "no key" in capsys.readouterr().err
    engine.assert_not_called()
