import json
from anthropic import Anthropic
from config import load_config


def translate(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None, industry: str = None) -> str:
    """
    Translate text between languages using configured provider
    
    Args:
        text: Text to translate
        from_lang: Source language (e.g., 'English', 'Spanish')
        to_lang: Target language
        target_gender: Gender of recipient for grammatical accuracy (male/female/other)
        conversation_history: Recent conversation messages for context
        industry: Industry key for context (e.g., 'dairy_farm', 'construction')
    
    Returns:
        Translated text
    """
    config = load_config()
    provider = config.get('translation_provider', 'claude')
    
    if provider == 'claude':
        return translate_with_claude(text, from_lang, to_lang, target_gender, conversation_history, industry)
    elif provider == 'gemini':
        return translate_with_gemini(text, from_lang, to_lang, target_gender, conversation_history, industry)
    elif provider == 'openai':
        return translate_with_openai(text, from_lang, to_lang, target_gender, conversation_history, industry)
    else:
        raise ValueError(f"Unknown provider: {provider}")

def build_translation_prompt(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None, industry: str = None) -> str:
    """Build translation prompt with context, gender, and conversation history"""
    config = load_config()
    
    # Get industry context
    if industry:
        industries = config.get('industries', {})
        industry_info = industries.get(industry, industries.get('other', {}))
        industry_name = industry_info.get('name', 'workplace')
        description = industry_info.get('description', 'workplace communication')
    else:
        industry_name = 'workplace'
        description = 'workplace communication'
    
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
    
    prompt = f"""You are a specialized translator for {industry_name} communications.

Context: {description}

Translate from {from_lang} to {to_lang}.{gender_instruction}{history_context}

Rules:
- Translate the message naturally and conversationally
- For greetings and casual messages (like "What's up?", "How are you?", "Hello"), translate them as natural conversational greetings in {to_lang}
- For questions - translate the QUESTION itself - do NOT answer it
- Use industry-specific terminology appropriate for {industry_name}
- Use conversation history to understand pronouns (he/she/it) and references and the overall context.
- Maintain natural workplace communication tone
- Return ONLY the translated message, nothing else

Text to translate:
{text}"""
    
    return prompt

def translate_with_claude(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None, industry: str = None) -> str:
    """Translate using Claude API with context and gender awareness"""
    config = load_config()
    claude_config = config['claude']
    
    client = Anthropic(api_key=claude_config['api_key'])
    
    prompt = build_translation_prompt(text, from_lang, to_lang, target_gender, conversation_history, industry)
    
    response = client.messages.create(
        model=claude_config['model'],
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return response.content[0].text.strip()

def translate_with_gemini(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None, industry: str = None) -> str:
    """Translate using Google Gemini 2.5 Flash Lite"""
    try:
        import google.generativeai as genai
        import typing_extensions as typing
    except ImportError:
        raise ImportError("Please install: pip install google-generativeai>=0.8.0 typing-extensions")
    
    config = load_config()
    gemini_config = config['gemini']
    
    # Define strict schema
    class TranslationResponse(typing.TypedDict):
        original_text: str
        translated_text: str
        detected_language: str
    
    # Configure Gemini
    genai.configure(api_key=gemini_config['api_key'])
    
    system_instruction = build_translation_prompt("", from_lang, to_lang, target_gender, conversation_history, industry).split("Text to translate:")[0]
    
    model = genai.GenerativeModel(
        model_name=gemini_config['model'],
        system_instruction=system_instruction,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": TranslationResponse,
            "temperature": 0.3 # Lower temperature is better for translation accuracy
        }
    )
    
    response = model.generate_content(f"Translate: {text}")
    
    # Parse JSON response
    result = json.loads(response.text)
    return result['translated_text']

def translate_with_openai(text: str, from_lang: str, to_lang: str, target_gender: str = None, conversation_history: list = None, industry: str = None) -> str:
    """Translate using OpenAI API"""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please install: pip install openai")
    
    config = load_config()
    openai_config = config['openai']
    
    client = OpenAI(api_key=openai_config['api_key'])
    
    prompt = build_translation_prompt(text, from_lang, to_lang, target_gender, conversation_history, industry)
    
    response = client.chat.completions.create(
        model=openai_config['model'],
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content.strip()

def generate_daily_actionitems(messages: list, industry: str = None) -> str:
    """
    Generate AI-powered summary of conversation messages
    Extracts action items only (tasks, safety issues, equipment problems)
    
    Args:
        messages: List of message dicts with 'from', 'text', 'lang', 'timestamp'
        industry: Industry key for context (e.g., 'dairy_farm', 'construction')
    
    Returns:
        Formatted summary as string
    """
    if not messages:
        return "No messages found in the last 24 hours.\n\nStart a conversation with your worker to see summaries here!"
    
    config = load_config()
    
    # Get industry context
    if industry:
        industries = config.get('industries', {})
        industry_info = industries.get(industry, industries.get('other', {}))
        industry_name = industry_info.get('name', 'workplace')
        description = industry_info.get('description', 'workplace communication')
    else:
        industry_name = 'workplace'
        description = 'workplace communication'
    
    # Format messages for prompt
    conversation_text = ""
    for msg in messages:
        timestamp = msg.get('timestamp', '')
        if timestamp:
            # Format timestamp nicely
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M')
            except:
                time_str = timestamp[:16] if len(timestamp) >= 16 else timestamp
        else:
            time_str = "Unknown time"
        
        conversation_text += f"[{time_str}] {msg['text']} ({msg['lang']})\n"
    
    # Build prompt
    prompt = f"""You are analyzing a {industry_name} workplace conversation.

Context: {description}

Conversation (last 24 hours):
{conversation_text}

Extract ONLY action items from this conversation. Focus on:
• Tasks to be completed
• Safety issues or concerns
• Equipment problems or maintenance needs
• Important instructions or requests

Skip: greetings, confirmations, casual conversation, questions already answered.

Format your response as a bullet list under appropriate categories:
- Action Items
- Safety Issues (if any)
- Equipment (if any)

If there are NO action items, respond with: "No action items found."

Be concise and specific. Extract only what requires follow-up action."""

    # Use Claude for summary generation (best quality)
    claude_config = config.get('claude', {})
    api_key = claude_config.get('api_key')
    
    if not api_key:
        return "Error: Claude API key not configured for summary generation."
    
    client = Anthropic(api_key=api_key)
    
    try:
        response = client.messages.create(
            model=claude_config.get('model', 'claude-sonnet-4-20250514'),
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        return response.content[0].text.strip()
    except Exception as e:
        return f"Error generating summary: {str(e)}"