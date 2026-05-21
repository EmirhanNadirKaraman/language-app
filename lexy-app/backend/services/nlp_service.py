import spacy
from spacy.language import Language

_LANG_MODEL_MAP: dict[str, str] = {
    "en": "en_core_web_sm",
    "de": "de_core_news_sm",
    "fr": "fr_core_news_sm",
    "es": "es_core_news_sm",
    "it": "it_core_news_sm",
    "pt": "pt_core_news_sm",
    "ja": "ja_core_news_sm",
    "ru": "ru_core_news_sm",
    "ko": "ko_core_news_sm",
    "pl": "pl_core_news_sm",
    "sv": "sv_core_news_sm",
}


class NLPService:
    """Loads and caches spaCy models per language, and manipulates sentences."""

    _models: dict[str, Language] = {}

    @classmethod
    def get_model(cls, language: str) -> Language:
        if language not in cls._models:
            if language not in _LANG_MODEL_MAP:
                raise ValueError(f"No spaCy model available for language: {language!r}")
            cls._models[language] = spacy.load(_LANG_MODEL_MAP[language])
        return cls._models[language]

    @classmethod
    def remove_word(cls, language: str, sentence: str, word: str, pos: str | None = None) -> str:
        """Replace the first matching token of `word` in `sentence` with '_'.

        If `pos` is provided, only replaces a token that also matches that POS tag.
        """
        nlp = cls.get_model(language)
        tokens = [{"text": t.text, "pos": t.pos_} for t in nlp(sentence)]
        index = 0
        for token in tokens:
            matches = token["text"] == word and (pos is None or token["pos"] == pos)
            if matches:
                index += sentence[index:].find(word)
                sentence = sentence[:index] + "_" + sentence[index + len(word):]
            else:
                index += len(token["text"])
        return sentence
