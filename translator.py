import json
from anthropic import Anthropic

def load_config():
    """Load API keys from config"""
    with open('config.json', 'r') as f:
        return json.load(f)

def translate(text: str, from_lang: str, to_lang: str, provider: str = "claude") -> str:
    """
    Translate text between languages
    
    Args:
        text: Text to translate
        from_lang: Source language (e.g., 'English', 'Spanish')
        to_lang: Target language
        provider: Translation provider ('claude', 'openai', 'google' - extensible)
    
    Returns:
        Translated text
    """
    if provider == "claude":
        return translate_with_claude(text, from_lang, to_lang)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def translate_with_claude(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using Claude API"""
    config = load_config()
    client = Anthropic(api_key=config['anthropic_api_key'])
    
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"Translate this text from {from_lang} to {to_lang}. Return ONLY the translation, nothing else:\n\n{text}"
        }]
    )
    
    return response.content[0].text.strip()