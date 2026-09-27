"""Topics in complaint narratives: NMF over TF-IDF, the path that needs nothing downloaded.

Each topic is named by its top terms, shown with example excerpts, and traced by month.
The narratives are the Bureau's, with personal details already replaced by XXXX; the
redaction marks and numbers are dropped before anything is counted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

EXTRA_STOP = frozenset(
    {
        "xxxx",
        "xx",
        "xxx",
        "xxxxxxxx",
        "would",
        "also",
        "told",
        "said",
        "get",
        "got",
        "one",
        "since",
        "still",
        "even",
    }
)
TOKENS = r"(?u)\b[a-z][a-z]{2,}\b"

# What a reader expects to find in bank complaints, and words that would mark each.
EXPECTED = {
    "Billing disputes": ("dispute", "charge", "charged", "refund", "billing"),
    "Credit reporting errors": (
        "report",
        "reporting",
        "inaccurate",
        "bureau",
        "bureaus",
        "equifax",
        "experian",
        "transunion",
    ),
    "Debt collection contact": ("collection", "collector", "debt", "calls", "calling"),
    "Fraud on an account": ("fraud", "fraudulent", "unauthorized", "stolen", "scam", "identity"),
}


@dataclass(frozen=True)
class TopicModel:
    terms: list[list[str]]  # top terms per topic
    weights: np.ndarray  # documents x topics, for the documents it was fitted on
    labels: list[str]
    vectorizer: TfidfVectorizer
    nmf: NMF

    def transform(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.nmf.transform(self.vectorizer.transform(texts)))


def opening(text: str, length: int = 120) -> str:
    """A narrative's first words, normalised: redaction marks, digits and spacing removed."""
    words = [w for w in text.lower().split() if w.strip("x.,:;()") != "" and not any(c.isdigit() for c in w)]
    return " ".join(words)[:length]


def templates(texts: list[str], min_copies: int = 5) -> tuple[np.ndarray, float]:
    """Which narratives open like at least ``min_copies`` others, and their share of the whole.

    Complaint narratives include form letters, many from credit repair services, filed
    word for word by different consumers. Counted as they are, they become topics of
    their own and drown out what individual consumers wrote.
    """
    keys = [opening(t) for t in texts]
    counts: dict[str, int] = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    is_template = np.array([counts[k] >= min_copies for k in keys])
    return is_template, float(is_template.mean())


def distinct(texts: list[str]) -> list[int]:
    """Indexes of the first narrative with each opening, so a form letter counts once."""
    seen: set[str] = set()
    keep = []
    for i, t in enumerate(texts):
        k = opening(t)
        if k not in seen:
            seen.add(k)
            keep.append(i)
    return keep


def fit_topics(texts: list[str], k: int, seed: int, top: int = 12) -> TopicModel:
    vectorizer = TfidfVectorizer(
        max_features=20_000,
        min_df=5,
        max_df=0.4,
        stop_words=sorted(ENGLISH_STOP_WORDS | EXTRA_STOP),
        token_pattern=TOKENS,
        sublinear_tf=True,
        lowercase=True,
    )
    x = vectorizer.fit_transform(texts)
    nmf = NMF(n_components=k, init="nndsvda", random_state=seed, max_iter=400)
    w = nmf.fit_transform(x)
    vocab = np.array(vectorizer.get_feature_names_out())
    terms = [vocab[np.argsort(-row)[:top]].tolist() for row in nmf.components_]
    labels = [", ".join(t[:4]) for t in terms]
    return TopicModel(terms=terms, weights=np.asarray(w), labels=labels, vectorizer=vectorizer, nmf=nmf)


def expected_topics(model: TopicModel, look: int = 12) -> list[tuple[str, int | None]]:
    """For each expected theme, the first topic whose top terms carry two of its marker words."""
    found: list[tuple[str, int | None]] = []
    for theme, words in EXPECTED.items():
        match = None
        for i, terms in enumerate(model.terms):
            if len(set(terms[:look]) & set(words)) >= 2:
                match = i
                break
        found.append((theme, match))
    return found


def excerpt(text: str, length: int = 180) -> str:
    """The narrative's opening, with any run of four or more digits masked like the Bureau's own redactions."""
    import re

    clean = re.sub(r"\d{4,}", "XXXX", " ".join(text.split()))
    if len(clean) <= length:
        return clean
    cut = clean[:length].rsplit(" ", 1)[0]
    return cut + " ..."


def topic_frame(frame: pl.DataFrame, weights: np.ndarray) -> pl.DataFrame:
    """Each complaint's dominant topic and that topic's weight in it."""
    dominant = weights.argmax(axis=1)
    strength = weights.max(axis=1)
    return frame.with_columns(topic=pl.Series(dominant.astype(np.int64)), topic_weight=pl.Series(strength))
