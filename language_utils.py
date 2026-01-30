"""Language detection and translation utilities for query handling."""

try:
    from langdetect import detect, detect_langs, LangDetectException
except ImportError:
    detect = None
    detect_langs = None
    LangDetectException = None


def detect_query_language(query_text: str) -> str:
    """
    Detect whether a query is in Dutch, English, or another language.
    Uses multiple heuristics to improve accuracy on short queries.

    Returns:
        'nl' (Dutch), 'en' (English), or 'other'
    """
    if not detect:
        # langdetect not available, check for English keywords
        return _fallback_language_detection(query_text)

    # First check for obvious English/Dutch indicators
    common_english_words = {
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "how",
        "why",
        "when",
        "where",
        "who",
        "which",
        "and",
        "or",
        "but",
        "for",
        "with",
        "in",
        "of",
        "to",
        "at",
        "by",
        "from",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "between",
        "among",
        "under",
        "over",
        "against",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
        "must",
        "shall",
    }

    common_dutch_words = {
        "de",
        "het",
        "een",
        "van",
        "in",
        "op",
        "voor",
        "met",
        "als",
        "dat",
        "te",
        "aan",
        "ook",
        "naar",
        "maar",
        "om",
        "tot",
        "door",
        "bij",
        "over",
        "was",
        "waren",
        "is",
        "zijn",
        "heeft",
        "hebben",
        "had",
        "hadden",
        "werd",
        "werden",
        "wordt",
        "worden",
        "kan",
        "kunnen",
        "moet",
        "moeten",
        "zal",
        "zullen",
        "zou",
        "zouden",
        "deze",
        "die",
        "dit",
        "wat",
        "wie",
    }

    words = query_text.lower().split()
    english_count = sum(1 for w in words if w in common_english_words)
    dutch_count = sum(1 for w in words if w in common_dutch_words)

    # If we have strong keyword indicators, trust them
    if english_count > 0 and dutch_count == 0:
        return "en"
    elif dutch_count > 0 and english_count == 0:
        return "nl"
    elif english_count > dutch_count:
        return "en"
    elif dutch_count > english_count:
        return "nl"

    # Try langdetect with confidence check
    try:
        if detect_langs:
            # Use detect_langs to get confidence scores
            langs = detect_langs(query_text)
            if langs:
                top_lang = langs[0]
                # Only trust if confidence is reasonably high (>0.7)
                if top_lang.prob > 0.7:
                    if top_lang.lang == "nl":
                        return "nl"
                    elif top_lang.lang in ("en", "en-US", "en-GB"):
                        return "en"
                    else:
                        return "other"

        # Fallback to simple detect
        lang = detect(query_text)
        if lang == "nl":
            return "nl"
        elif lang in ("en", "en-US", "en-GB"):
            return "en"
        else:
            return "other"

    except (LangDetectException, Exception):
        # If detection fails, use keyword-based fallback
        return _fallback_language_detection(query_text)


def _fallback_language_detection(query_text: str) -> str:
    """
    Fallback language detection based on character patterns and keywords.
    Returns 'en' for English, 'nl' for Dutch, or 'other'.
    """
    query_lower = query_text.lower()

    # English indicators
    english_patterns = [
        " the ",
        " a ",
        " an ",
        " is ",
        " are ",
        " was ",
        " were ",
        " what ",
        " how ",
        " why ",
        " when ",
        " where ",
    ]

    # Dutch indicators
    dutch_patterns = [
        " de ",
        " het ",
        " een ",
        " van ",
        " voor ",
        " naar ",
        " met ",
        " als ",
        " dat ",
        " was ",
        " waren ",
    ]

    english_matches = sum(1 for p in english_patterns if p in f" {query_lower} ")
    dutch_matches = sum(1 for p in dutch_patterns if p in f" {query_lower} ")

    if english_matches > dutch_matches:
        return "en"
    elif dutch_matches > english_matches:
        return "nl"
    else:
        # Default to English for ambiguous cases (more international audience)
        return "en"


def get_queries_for_compare_mode(query_text: str, client) -> dict:
    """
    For 'Compare Both' mode, prepare queries for both Dutch and English embeddings.
    Each embedding is queried in its native language.

    Logic:
    - If query is Dutch: use as-is for Dutch embeddings, translate to English for English embeddings
    - If query is English: translate to Dutch for Dutch embeddings, use as-is for English embeddings
    - If query is other language: translate to Dutch for Dutch embeddings, translate to English for English embeddings

    Args:
        query_text: The original query
        client: OpenAI client for translation

    Returns:
        dict with keys 'dutch_query' and 'english_query'
    """
    detected_lang = detect_query_language(query_text)

    if detected_lang == "nl":
        # Query is Dutch
        dutch_query = query_text
        english_query = _translate_query(query_text, "modern English", client)
    elif detected_lang == "en":
        # Query is English
        dutch_query = _translate_query(query_text, "modern Dutch", client)
        english_query = query_text
    else:
        # Query is in another language
        dutch_query = _translate_query(query_text, "modern Dutch", client)
        english_query = _translate_query(query_text, "modern English", client)

    return {
        "dutch_query": dutch_query,
        "english_query": english_query,
        "detected_lang": detected_lang,
    }


def get_query_for_mode(query_text: str, mode: str, client) -> dict:
    """
    Prepare a single query for a specific embedding mode.

    Args:
        query_text: Original query
        mode: 'original' (Dutch) or 'translated' (English)
        client: OpenAI client for translation

    Returns:
        dict with keys 'query' and 'detected_lang'
    """
    detected_lang = detect_query_language(query_text)

    if mode == "original":
        if detected_lang == "nl":
            query = query_text
        else:
            query = _translate_query(query_text, "modern Dutch", client)
    elif mode == "translated":
        if detected_lang == "en":
            query = query_text
        else:
            query = _translate_query(query_text, "modern English", client)
    else:
        query = query_text

    return {"query": query, "detected_lang": detected_lang}


def _translate_query(text: str, target_language: str, client) -> str:
    """
    Translate a query to target language using OpenAI.

    Args:
        text: Text to translate
        target_language: Target language (e.g., "modern Dutch", "modern English")
        client: OpenAI client

    Returns:
        Translated text
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": f"Translate this search query to {target_language}. Return only the translation, nothing else:\n\n{text}",
                }
            ],
            temperature=0.3,
            max_tokens=100,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Translation failed: {e}. Using original query.")
        return text
