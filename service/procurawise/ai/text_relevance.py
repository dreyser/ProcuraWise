import re

_WORD_RE = re.compile(r"[a-záéíóúñ0-9]+", re.IGNORECASE)


def keywords(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if len(word) > 2}


def relevance(query_keywords: set[str], candidate_text: str) -> int:
    return len(query_keywords & keywords(candidate_text))
