import json
import os
from typing import Dict, Any, Optional

class I18n:
    """Internationalization handler for BridgeOS bot messages"""
    
    def __init__(self):
        self._translations: Dict[str, Dict] = {}
        self._language_mapping: Dict[str, str] = {}
        self._load_language_mapping()
    
    def _load_language_mapping(self):
        """Load language mapping from config.json"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._language_mapping = config.get('language_mapping', {})
        except Exception as e:
            print(f"Warning: Could not load language mapping from config.json: {e}")
            # Fallback to empty mapping
            self._language_mapping = {}
    
    def _get_language_code(self, language: str) -> str:
        """
        Convert display language name to language code
        
        Args:
            language: Display name (e.g., "עברית", "English", "Español")
        
        Returns:
            Language code (e.g., "he", "en", "es")
        """
        return self._language_mapping.get(language, 'en')
    
    def _load_translation_file(self, language_code: str) -> Optional[Dict]:
        """
        Load translation JSON file for a language code
        
        Args:
            language_code: ISO 639-1 code (e.g., "en", "he", "ar")
        
        Returns:
            Dictionary of translations, or None if file not found
        """
        # Check if already cached
        if language_code in self._translations:
            return self._translations[language_code]
        
        # Try to load from file
        file_path = os.path.join('locales', f'{language_code}.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translations = json.load(f)
                self._translations[language_code] = translations
                return translations
        except FileNotFoundError:
            print(f"Warning: Translation file not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {file_path}: {e}")
            return None
        except Exception as e:
            print(f"Error loading translation file {file_path}: {e}")
            return None
    
    def _get_nested_value(self, data: Dict, key_path: str) -> Optional[str]:
        """
        Get value from nested dictionary using dot notation
        
        Args:
            data: Dictionary to search
            key_path: Dot-separated path (e.g., "start.welcome_back")
        
        Returns:
            String value if found, None otherwise
        """
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        
        return current if isinstance(current, str) else None
    
    def get_text(self, language: str, key_path: str, default: str = "", **kwargs) -> str:
        """
        Get translated text with fallback system
        
        Args:
            language: Display language name (e.g., "עברית", "English")
            key_path: Dot-separated path to translation key (e.g., "start.welcome_back")
            default: Default text if translation not found
            **kwargs: Variables to format into the string (e.g., role="manager")
        
        Returns:
            Translated and formatted text
        
        Fallback order:
            1. Requested language translation
            2. English translation
            3. Default value provided
        """
        # Convert language name to code
        language_code = self._get_language_code(language)
        
        # Try to get translation in requested language
        translations = self._load_translation_file(language_code)
        if translations:
            text = self._get_nested_value(translations, key_path)
            if text:
                try:
                    return text.format(**kwargs)
                except KeyError as e:
                    print(f"Warning: Missing placeholder in translation {key_path}: {e}")
                    return text
        
        # Fallback to English if not found or not the requested language
        if language_code != 'en':
            english_translations = self._load_translation_file('en')
            if english_translations:
                text = self._get_nested_value(english_translations, key_path)
                if text:
                    try:
                        return text.format(**kwargs)
                    except KeyError as e:
                        print(f"Warning: Missing placeholder in English translation {key_path}: {e}")
                        return text
        
        # Final fallback to default value
        if default:
            try:
                return default.format(**kwargs)
            except KeyError as e:
                print(f"Warning: Missing placeholder in default text {key_path}: {e}")
                return default
        
        # If everything fails, return empty string
        print(f"Error: No translation found for {key_path} and no default provided")
        return ""


# Global instance
_i18n_instance = I18n()


def get_text(language: str, key_path: str, default: str = "", **kwargs) -> str:
    """
    Convenience function to get translated text
    
    Usage:
        from i18n import get_text
        
        text = get_text(
            user['language'],
            'start.welcome_back',
            default="Welcome back! You're registered as {role}.",
            role=user['role']
        )
    
    Args:
        language: Display language name (e.g., "עברית", "English")
        key_path: Dot-separated path to translation key
        default: Default text if translation not found
        **kwargs: Variables to format into the string
    
    Returns:
        Translated and formatted text
    """
    return _i18n_instance.get_text(language, key_path, default, **kwargs)


def reload_translations():
    """
    Reload all translation files (useful for testing or hot-reloading)
    """
    global _i18n_instance
    _i18n_instance = I18n()