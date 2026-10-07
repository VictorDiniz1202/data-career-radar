"""Title pre-filter that gates paid LLM calls."""

import pytest

from career_radar.normalization.job_family import is_data_role


@pytest.mark.parametrize(
    "title",
    [
        "Data Engineer",
        "Senior Data Analyst (Remote)",
        "Analytics Engineer",
        "Staff Machine Learning Engineer",
        "ML Engineer",
        "Business Intelligence Developer",
        "BI Analyst",
        "Data Scientist, Growth",
        "Research Scientist",
        "Engenheiro de Dados Sênior",
        "Analista de Dados Pleno",
        "Estatístico",
        "Product Analytics Lead",
    ],
)
def test_data_titles_are_kept(title):
    assert is_data_role(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Account Executive",
        "Sales Development Representative",
        "Senior Recruiter",
        "Software Engineer",
        "Sales Engineer",
        "Biology Lab Technician",
        "HTML Developer",
        "Data Center Technician",
        "Data Entry Clerk",
        "",
        None,
    ],
)
def test_other_titles_are_dropped(title):
    assert is_data_role(title) is False
