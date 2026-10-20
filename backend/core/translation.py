"""
translation.py
──────────────
Offline neural translation using Helsinki-NLP MarianMT models.
Models are lazy-loaded and cached per language pair to avoid reloading
on every request.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)

# Supported source languages → model suffix mapping (X → English)
# Full list: https://huggingface.co/Helsinki-NLP
_LANG_TO_EN: dict[str, str] = {
    "fr": "fr-en",
    "de": "de-en",
    "es": "es-en",
    "it": "it-en",
    "pt": "pt-en",
    "nl": "nl-en",
    "ru": "ru-en",
    "zh": "zh-en",
    "ja": "jap-en",
    "ko": "ko-en",
    "ar": "ar-en",
    "hi": "hi-en",
    "ta": "ta-en",
    "tr": "tr-en",
    "pl": "pl-en",
}

# English → target language model suffixes
_EN_TO_LANG: dict[str, str] = {
    "fr": "en-fr",
    "de": "en-de",
    "es": "en-es",
    "it": "en-it",
    "pt": "en-pt",
    "nl": "en-nl",
    "ru": "en-ru",
    "zh": "en-zh",
    "ja": "en-jap",
    "ko": "en-ko",
    "ar": "en-ar",
    "hi": "en-hi",
    "ta": "en-ta",
    "tr": "en-tr",
    "pl": "en-pl",
}


@lru_cache(maxsize=8)
def _load_pipeline(model_name: str):
    """Load and cache a MarianMT tokenizer + model pair."""
    from transformers import MarianMTModel, MarianTokenizer

    logger.info("Loading translation model %s …", model_name)
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    model = MarianMTModel.from_pretrained(model_name)
    return tokenizer, model


class Translator:
    """Translates text between language pairs using offline MarianMT."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def translate(self, text: str, source_lang: str, target_lang: str = "en") -> Optional[str]:
        """
        Translate text from source_lang to target_lang.
        Supports any → English and English → any via MarianMT.
        Returns None if the pair is unsupported or source == target.
        """
        if not text or not text.strip():
            return None

        src = (source_lang or "en").lower()
        tgt = (target_lang or "en").lower()

        if src == tgt:
            logger.debug("Translation skipped: source '%s' == target '%s'", src, tgt)
            return None

        # Resolve model suffix
        if tgt == "en":
            # X → English
            pair = _LANG_TO_EN.get(src)
            if pair is None:
                logger.warning("No MarianMT model for '%s' → 'en'; skipping", src)
                return None
        elif src == "en":
            # English → X
            pair = _EN_TO_LANG.get(tgt)
            if pair is None:
                logger.warning("No MarianMT model for 'en' → '%s'; skipping", tgt)
                return None
        else:
            # X → Y: pivot through English (two hops)
            en_text = self.translate(text, src, "en")
            if en_text is None:
                return None
            return self.translate(en_text, "en", tgt)

        model_name = f"Helsinki-NLP/opus-mt-{pair}"
        tokenizer, model = _load_pipeline(model_name)

        inputs = tokenizer([text], return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = model.generate(**inputs)
        decoded = tokenizer.decode(translated[0], skip_special_tokens=True)
        return decoded or None
