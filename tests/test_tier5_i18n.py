"""
Tier 5: i18n validation — locale file integrity.

Tests:
  1. Every key referenced in handler code exists in en.json
  2. All locale files have the same key structure
  3. Format string placeholders match between languages
  4. No empty translation values
"""
import pytest
import json
import os
import re
from pathlib import Path


# ====================================================================
# FIXTURES
# ====================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES_DIR = os.path.join(PROJECT_ROOT, "locales")


def load_locale(lang_code: str) -> dict:
    """Load a locale JSON file."""
    path = os.path.join(LOCALES_DIR, f"{lang_code}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten nested dict into dot-separated keys.
    e.g. {"start": {"welcome_back": "Hi"}} → {"start.welcome_back": "Hi"}
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep))
        else:
            items[new_key] = v
    return items


def extract_placeholders(text: str) -> set:
    """Extract {placeholder} names from a format string."""
    return set(re.findall(r"\{(\w+)\}", text))


@pytest.fixture(scope="module")
def en_locale():
    return load_locale("en")


@pytest.fixture(scope="module")
def en_flat(en_locale):
    return flatten_dict(en_locale)


@pytest.fixture(scope="module")
def all_locales():
    """Load all available locale files."""
    locales = {}
    if not os.path.isdir(LOCALES_DIR):
        return locales
    for f in os.listdir(LOCALES_DIR):
        if f.endswith(".json"):
            lang = f.replace(".json", "")
            locales[lang] = load_locale(lang)
    return locales


# ====================================================================
# HANDLER KEY EXTRACTION
# ====================================================================

def extract_get_text_keys_from_handlers() -> set:
    """
    Scan handler files for get_text() calls and extract the key_path arguments.
    Pattern: get_text(..., 'some.key.path', ...)
    """
    handlers_dir = os.path.join(PROJECT_ROOT, "handlers")
    keys = set()

    if not os.path.isdir(handlers_dir):
        return keys

    # Match both get_text(language, 'key.path', ...) and get_text('English', 'key.path', ...)
    pattern = re.compile(r"get_text\([^,]+,\s*['\"]([^'\"]+)['\"]")

    for filename in os.listdir(handlers_dir):
        if filename.endswith(".py"):
            filepath = os.path.join(handlers_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            matches = pattern.findall(content)
            keys.update(matches)

    return keys


# ====================================================================
# TESTS
# ====================================================================

class TestEnJsonCompleteness:
    """Every key referenced in handler code must exist in en.json."""

    def test_all_handler_keys_exist_in_en(self, en_flat):
        """
        Scan handlers/ for get_text('key.path') calls,
        verify each key exists in en.json.
        """
        handler_keys = extract_get_text_keys_from_handlers()
        if not handler_keys:
            pytest.skip("No handler files found or no get_text calls detected")

        missing = []
        for key in sorted(handler_keys):
            if key not in en_flat:
                missing.append(key)

        if missing:
            pytest.fail(
                f"Keys referenced in handlers but missing from en.json:\n"
                + "\n".join(f"  - {k}" for k in missing)
            )


class TestLocaleStructureConsistency:
    """All locale files should have the same key structure as en.json."""

    def test_all_locales_have_same_keys(self, all_locales):
        """Every key in en.json should exist in every other locale file."""
        if not all_locales or "en" not in all_locales:
            pytest.skip("en.json not found in locales/")

        en_keys = set(flatten_dict(all_locales["en"]).keys())

        for lang, data in all_locales.items():
            if lang == "en":
                continue
            lang_keys = set(flatten_dict(data).keys())
            missing = en_keys - lang_keys
            extra = lang_keys - en_keys

            if missing:
                pytest.fail(
                    f"{lang}.json is missing keys present in en.json:\n"
                    + "\n".join(f"  - {k}" for k in sorted(missing)[:20])
                    + (f"\n  ... and {len(missing) - 20} more" if len(missing) > 20 else "")
                )

    def test_no_extra_keys_in_translations(self, all_locales):
        """Non-English locales shouldn't have keys that don't exist in en.json."""
        if not all_locales or "en" not in all_locales:
            pytest.skip("en.json not found")

        en_keys = set(flatten_dict(all_locales["en"]).keys())

        for lang, data in all_locales.items():
            if lang == "en":
                continue
            lang_keys = set(flatten_dict(data).keys())
            extra = lang_keys - en_keys
            if extra:
                # Warning, not failure — extra keys are less critical
                print(f"WARNING: {lang}.json has extra keys not in en.json: {sorted(extra)[:10]}")


class TestPlaceholderConsistency:
    """Format string placeholders ({name}, {code}) must match across locales."""

    def test_placeholders_match(self, all_locales):
        """Every locale's placeholders must match en.json's placeholders."""
        if not all_locales or "en" not in all_locales:
            pytest.skip("en.json not found")

        en_flat = flatten_dict(all_locales["en"])
        mismatches = []

        for lang, data in all_locales.items():
            if lang == "en":
                continue
            lang_flat = flatten_dict(data)

            for key, en_value in en_flat.items():
                if not isinstance(en_value, str):
                    continue
                en_placeholders = extract_placeholders(en_value)
                if not en_placeholders:
                    continue

                lang_value = lang_flat.get(key)
                if not lang_value or not isinstance(lang_value, str):
                    continue

                lang_placeholders = extract_placeholders(lang_value)
                if en_placeholders != lang_placeholders:
                    mismatches.append(
                        f"  {lang}.{key}: en={en_placeholders}, {lang}={lang_placeholders}"
                    )

        if mismatches:
            pytest.fail(
                "Placeholder mismatches between en.json and translations:\n"
                + "\n".join(mismatches[:20])
            )


class TestNoEmptyTranslations:
    """No translation value should be an empty string."""

    def test_no_empty_values(self, all_locales):
        for lang, data in all_locales.items():
            flat = flatten_dict(data)
            empty = [k for k, v in flat.items() if isinstance(v, str) and v.strip() == ""]
            if empty:
                pytest.fail(
                    f"{lang}.json has empty translation values:\n"
                    + "\n".join(f"  - {k}" for k in empty[:20])
                )


class TestEnJsonFormat:
    """Basic format validation for en.json."""

    def test_en_json_is_valid_json(self):
        path = os.path.join(LOCALES_DIR, "en.json")
        if not os.path.exists(path):
            pytest.skip("en.json not found")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_en_json_has_expected_top_level_keys(self, en_locale):
        """en.json should have the core sections used by handlers."""
        expected = {"start", "registration", "help", "reset", "daily",
                    "subscription", "tasks", "handle_message", "menu"}
        actual = set(en_locale.keys())
        missing = expected - actual
        if missing:
            pytest.fail(f"en.json missing expected top-level keys: {missing}")
