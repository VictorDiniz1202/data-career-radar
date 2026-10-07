"""Cheap, deterministic title pre-filter: is this posting in the data family?

It only decides whether a posting is worth a paid LLM call. It is not a
classification of seniority, fit or eligibility. Matching is on the title alone
and stays conservative: an unfamiliar title is a False, never a guess.
"""

import re
import unicodedata

# Terms that put a title in the data family (whole words/phrases only, so "bi"
# does not match "biology" and "ml" does not match "html").
_DATA_TERMS = re.compile(
    r"\b("
    r"data|dados|dataops|analytics|analytic|"
    r"business intelligence|bi|etl|elt|"
    r"machine learning|ml|mlops|"
    r"scientist|cientista|statistician|estatistico"
    r")\b"
)
# Titles where "data" is incidental to a non-analytical job.
_NOT_DATA = re.compile(r"\bdata (?:center|centre|entry)\b")


def _fold(text: str) -> str:
    """Lowercase and strip accents so 'Estatístico' matches 'estatistico'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def is_data_role(title: str | None) -> bool:
    """True when the job title belongs to the data family (engineering,
    analytics/BI, science/ML); False for everything else, including no title.
    """
    if not title:
        return False
    folded = _fold(title)
    if _NOT_DATA.search(folded):
        return False
    return _DATA_TERMS.search(folded) is not None
