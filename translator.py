import json
from anthropic import Anthropic

def load_config():
    """Load API keys and settings from config"""
    with open('config.json', 'r') as f:
        return json.load(f)

def translate(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None) -> str:
    """
    Translate text between languages using configured provider
    
    Args:
        text: Text to translate
        from_lang: Source language (e.g., 'English', 'Spanish')
        to_lang: Target language
        target_gender: Gender of recipient for grammatical accuracy (male/female/other)
        conversation_history: Recent conversation messages for context
    
    Returns:
        Translated text
    """
    config = load_config()
    provider = config.get('translation_provider', 'claude')
    
    if provider == 'claude':
        return translate_with_claude(text, from_lang, to_lang, target_gender, conversation_history)
    elif provider == 'gemini':
        return translate_with_gemini(text, from_lang, to_lang, target_gender, conversation_history)
    elif provider == 'openai':
        return translate_with_openai(text, from_lang, to_lang, target_gender, conversation_history)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def build_translation_prompt(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None) -> str:
    """Build translation prompt with context, gender, and conversation history"""
    config = load_config()
    context = config.get('context', {})
    industry = context.get('industry', 'workplace')
    description = context.get('description', 'workplace communication')
    
    gender_instruction = ""
    if target_gender and target_gender.lower() in ['male', 'female']:
        gender_instruction = f"\nThe recipient is {target_gender}. Use appropriate gendered grammar for {to_lang}."
    
    # Format conversation history
    history_context = ""
    if conversation_history and len(conversation_history) > 0:
        history_context = "\n\nRecent conversation for context:\n"
        for msg in conversation_history:
            history_context += f"- {msg['text']} ({msg['lang']})\n"
        history_context += "\nUse this context to understand pronouns, references, and topic continuity.\n"
    
    prompt = f"""You are a specialized translator for {industry} communications.

Context: {description}

Translate from {from_lang} to {to_lang}.{gender_instruction}{history_context}

Rules:
- ONLY translate the text, do NOT answer questions or provide information
- Use industry-specific terminology appropriate for {industry}
- Use conversation history to understand pronouns (he/she/it) and references
- If someone asks "Where is X?", translate the QUESTION, don't answer it
- Maintain professional workplace tone
- Return ONLY the translation, nothing else

Text to translate:
{text}"""
    
    return prompt

def translate_with_claude(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None) -> str:
    """Translate using Claude API with context and gender awareness"""
    config = load_config()
    claude_config = config['claude']
    
    client = Anthropic(api_key=claude_config['api_key'])
    
    prompt = build_translation_prompt(text, from_lang, to_lang, target_gender, conversation_history)
    
    response = client.messages.create(
        model=claude_config['model'],
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return response.content[0].text.strip()

def translate_with_gemini(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None) -> str:
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
    
    system_instruction = build_translation_prompt("", from_lang, to_lang, target_gender, conversation_history).split("Text to translate:")[0]
    
    model = genai.GenerativeModel(
        model_name=gemini_config['model'],
        system_instruction=system_instruction,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": TranslationResponse
        }
    )
    
    response = model.generate_content(f"Translate: {text}")
    
    # Parse JSON response
    result = json.loads(response.text)
    return result['translated_text']

def translate_with_openai(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None) -> str:
    """Translate using OpenAI API"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please install: pip install openai")
    
    config = load_config()
    openai_config = config['openai']
    
    client = OpenAI(api_key=openai_config['api_key'])
    
    prompt = build_translation_prompt(text, from_lang, to_lang, target_gender, conversation_history)
    
    response = client.chat.completions.create(
        model=openai_config['model'],
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content.strip()