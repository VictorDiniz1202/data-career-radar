"""Small, deterministic location hints; never a residency eligibility check."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

CountryCode = Literal["BR", "US"]

_REMOTE = re.compile(r"\b(remote|remoto|remota|anywhere|worldwide)\b")
_NOT_REMOTE = re.compile(r"\b(?:not|non|no|nao|sem)[\s-]+(?:remote|remoto|remota)\b")
_COUNTRIES = {
    "BR": re.compile(r"\b(brasil|brazil|br)\b"),
    "US": re.compile(r"\b(united states(?: of america)?|estados unidos|usa|us)\b"),
}
_CITIES = {
    "BR": re.compile(r"\b(sao paulo|rio de janeiro|belo horizonte|brasilia)\b"),
    "US": re.compile(r"\b(new york|san francisco|los angeles|seattle)\b"),
}
# Only classify text fully understood by this small dictionary. An unfamiliar
# second location must not disappear behind a known country (e.g. BR / Spain).
_MODIFIERS = re.compile(r"\b(hybrid|onsite|on site|presencial|only|sp|rj|ny)\b")


@dataclass(frozen=True)
class NormalizedLocation:
    is_remote: bool
    country_code: CountryCode | None


def normalize_location(
    location_raw: str | None, is_remote: bool = False
) -> NormalizedLocation:
    """Combine a provider remote hint with conservative BR/US text rules.

    Unknown locations, unsupported countries and conflicting hints return None.
    A provider's positive remote flag takes precedence over textual negation.
    """
    value = unicodedata.normalize("NFKD", location_raw or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = re.sub(r"\bu\.?s\.?a\.?\b", "usa", value)
    value = re.sub(r"\bu\.s\b\.?", "us", value)
    remote = is_remote or bool(_REMOTE.search(_NOT_REMOTE.sub("", value)))
    countries = {
        code
        for patterns in (_COUNTRIES, _CITIES)
        for code, pattern in patterns.items()
        if pattern.search(value)
    }
    remaining = _REMOTE.sub("", _NOT_REMOTE.sub("", value))
    for pattern in (*_COUNTRIES.values(), *_CITIES.values(), _MODIFIERS):
        remaining = pattern.sub("", remaining)
    country: CountryCode | None = None
    if len(countries) == 1 and not any(c.isalpha() for c in remaining):
        country = "BR" if "BR" in countries else "US"
    return NormalizedLocation(remote, country)
