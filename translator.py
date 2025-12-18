import json
from anthropic import Anthropic

def load_config():
    """Load API keys and settings from config"""
    with open('config.json', 'r') as f:
        return json.load(f)

def translate(text: str, from_lang: str, to_lang: str) -> str:
    """
    Translate text between languages using configured provider
    
    Args:
        text: Text to translate
        from_lang: Source language (e.g., 'English', 'Spanish')
        to_lang: Target language
    
    Returns:
        Translated text
    """
    config = load_config()
    provider = config.get('translation_provider', 'claude')
    
    if provider == 'claude':
        return translate_with_claude(text, from_lang, to_lang)
    elif provider == 'gemini':
        return translate_with_gemini(text, from_lang, to_lang)
    elif provider == 'openai':
        return translate_with_openai(text, from_lang, to_lang)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def translate_with_claude(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using Claude API with strong system prompt"""
    config = load_config()
    claude_config = config['claude']
    
    client = Anthropic(api_key=claude_config['api_key'])
    
    system_prompt = """You are a translator ONLY. Your job is to translate text, NOT to answer questions or provide information.

Rules:
- ONLY translate the text exactly as given
- Do NOT answer questions
- Do NOT add explanations
- Do NOT provide information
- If someone asks "Where is X?", translate the QUESTION, don't answer it
- Return ONLY the translation, nothing else

Examples:
Input: "Where is Kibbutz Afikim?"
CORRECT: "איפה קיבוץ אפיקים?"
WRONG: "Kibbutz Afikim is near the Sea of Galilee"

Input: "What time is it?"
CORRECT: "¿Qué hora es?"
WRONG: "I don't have access to current time"
"""
    
    response = client.messages.create(
        model=claude_config['model'],
        max_tokens=1000,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Translate from {from_lang} to {to_lang}:\n\n{text}"
        }]
    )
    
    return response.content[0].text.strip()

def translate_with_gemini(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using Google Gemini API with schema-enforced JSON"""
    try:
        import google.generativeai as genai
        import typing_extensions as typing
    except ImportError:
        raise ImportError("Please install: pip install google-generativeai typing-extensions")
    
    config = load_config()
    gemini_config = config['gemini']
    
    # Define strict schema
    class TranslationResponse(typing.TypedDict):
        original_text: str
        translated_text: str
        detected_language: str
    
    # Configure Gemini
    genai.configure(api_key=gemini_config['api_key'])
    
    model = genai.GenerativeModel(
        model_name=gemini_config['model'],
        system_instruction="You are a translation engine. Translate the input text accurately from the source language to the target language. Do NOT answer questions, only translate them.",
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": TranslationResponse
        }
    )
    
    prompt = f"Translate this text from {from_lang} to {to_lang}: {text}"
    response = model.generate_content(prompt)
    
    # Parse JSON response
    result = json.loads(response.text)
    return result['translated_text']

def translate_with_openai(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using OpenAI API"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please install: pip install openai")
    
    config = load_config()
    openai_config = config['openai']
    
    client = OpenAI(api_key=openai_config['api_key'])
    
    system_prompt = """You are a translator ONLY. Translate text exactly as given. Do NOT answer questions or provide information."""
    
    response = client.chat.completions.create(
        model=openai_config['model'],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Translate from {from_lang} to {to_lang}:\n\n{text}"}
        ]
    )
    
    return response.choices[0].message.content.strip()