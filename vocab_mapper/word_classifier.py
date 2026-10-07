"""Contextual English classification, aligned to Bookspine's word spans."""
from functools import lru_cache

MODEL = "en_core_web_sm"
FUNCTIONAL_POS = frozenset({"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "SCONJ"})


@lru_cache(maxsize=1)
def load_pipeline():
    try:
        import spacy
        return spacy.load(MODEL, exclude=["ner"])
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "Bookspine requires spaCy and en_core_web_sm. Install with "
            "python -m pip install spacy, then python -m spacy download en_core_web_sm."
        ) from exc


def classify_sentences(sentences):
    """Yield classes for regex matches while preserving original word positions.

    A contraction or hyphenated word is functional only if all overlapping
    linguistic components are functional. Other POS (including NUM/INTJ/X)
    remain semantic under the existing binary output schema.
    """
    if not sentences:
        return
    nlp = load_pipeline()
    for doc, matches in nlp.pipe(sentences, as_tuples=True, batch_size=64):
        classes = []
        cursor = 0
        tokens = list(doc)
        for match in matches:
            while cursor < len(tokens) and tokens[cursor].idx + len(tokens[cursor]) <= match.start():
                cursor += 1
            components = []
            index = cursor
            while index < len(tokens) and tokens[index].idx < match.end():
                token = tokens[index]
                if not token.is_punct and not token.is_space:
                    components.append(token)
                index += 1
            if not components or any(not token.pos_ for token in components):
                raise RuntimeError(f"spaCy returned no POS annotation for {match.group()!r}.")
            classes.append("functional" if all(t.pos_ in FUNCTIONAL_POS for t in components) else "semantic")
        yield classes
