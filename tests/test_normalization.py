import pytest

from career_radar.ingestion.models import JobPosting
from career_radar.normalization.location import normalize_location


@pytest.mark.parametrize(
    "raw,flag,remote,country",
    [
        ("São Paulo / SP / Brazil", False, False, "BR"),
        ("Remote U.S.", False, True, "US"),
        ("Remote U.S.A.", False, True, "US"),
        ("São Paulo", False, False, "BR"),
        ("Rio de Janeiro, Brasil", False, False, "BR"),
        ("New York", False, False, "US"),
        ("United States", False, False, "US"),
        ("Anywhere", False, True, None),
        ("Remote - LATAM", False, True, None),
        ("London", True, True, None),
        (None, False, False, None),
        (None, True, True, None),
        ("", False, False, None),
        ("Remote Brazil / US", False, True, None),
        ("Remote US / Canada", False, True, None),
        ("Remote Brazil / Spain", False, True, None),
        ("São Paulo / London", False, False, None),
        ("São Paulo / US", False, False, None),
        ("Remote - Austin, US", False, True, None),
        ("CA", False, False, None),
        ("SP", False, False, None),
        ("Columbus", False, False, None),
        ("Brussels", False, False, None),
        ("Not remote - Brazil", False, False, "BR"),
        ("Non-remote, US", False, False, "US"),
        ("Não remoto, Brasil", False, False, "BR"),
        ("REMOTO - BRASIL", False, True, "BR"),
        ("  Sa\u0303o Paulo  ", False, False, "BR"),
    ],
)
def test_normalization(raw, flag, remote, country):
    result = normalize_location(raw, flag)
    assert result.is_remote is remote
    assert result.country_code == country


def test_canonical_model_normalizes_and_preserves_raw_text():
    posting = JobPosting(
        source="greenhouse",
        board_slug="example",
        external_id="1",
        title="Engineer",
        url="https://example.com/job/1",
        location="São Paulo / SP / Brazil",
        is_remote=True,
    )
    assert posting.location == "São Paulo / SP / Brazil"
    assert posting.is_remote is True
    assert posting.country_code == "BR"
