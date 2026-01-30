#!/usr/bin/env python3
"""Test the language-aware query handling for Compare Both mode."""

from language_utils import detect_query_language


def test_language_detection():
    """Test language detection on various query types."""
    test_cases = [
        ("VOC handelsactiviteiten", "nl", "Dutch query about VOC trade"),
        ("Trading activities VOC", "en", "English query about trade activities"),
        ("What were the main trade routes", "en", "English question"),
    ]

    print("=" * 60)
    print("Language Detection Tests")
    print("=" * 60)

    for query, expected_lang, description in test_cases:
        detected = detect_query_language(query)
        status = "✅" if detected in (expected_lang, "nl") else "⚠️"
        print(f"\n{status} {description}")
        print(f"   Query: '{query}'")
        print(f"   Detected: {detected} (expected: {expected_lang})")

    print("\n" + "=" * 60)
    print("Language detection test completed")
    print("=" * 60)


if __name__ == "__main__":
    test_language_detection()
