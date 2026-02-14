import json
from anthropic import Anthropic
from config import load_config

_claude_client = None
_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
        except ImportError:
            raise ImportError("Please install: pip install google-genai")
        config = load_config()
        api_key = config['gemini'].get('api_key')
        if not api_key:
            raise ValueError("Gemini API key not configured.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        config = load_config()
        api_key = config['claude'].get('api_key')
        if not api_key:
            raise ValueError(
                "Claude API key not configured. "
                "Please set CLAUDE_API_KEY in Railway environment variables or secrets.json"
            )
        _claude_client = Anthropic(api_key=api_key)
    return _claude_client


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
            history_context += f"- {msg['text']}\n"
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
    
    client = _get_claude_client()
    
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
    """Translate using Google Gemini"""
    from google.genai import types
    
    config = load_config()
    gemini_config = config['gemini']
    
    client = _get_gemini_client()
    
    prompt = build_translation_prompt(text, from_lang, to_lang, target_gender, conversation_history, industry)
    
    response = client.models.generate_content(
        model=gemini_config['model'],
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
        )
    )
    
    return response.text.strip()

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

def generate_daily_actionitems(messages: list, industry: str = None, manager_language: str = None) -> str:
    """
    Generate AI-powered action items from conversation messages
    Extracts ONLY actionable tasks, safety issues, and equipment problems
    
    Args:
        messages: List of message dicts with 'from', 'text', 'lang', 'timestamp'
        industry: Industry key for context (e.g., 'dairy_farm', 'construction')
        manager_language: Manager's language for the output (e.g., 'English', 'עברית')
    
    Returns:
        Formatted bullet list of action items in manager's language
    """
    if not messages:
        return "No messages found in the last 24 hours.\n\nStart a conversation with your worker to see action items here!"
    
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
    
    # Default to English if not specified
    output_language = manager_language or 'English'
    
    # Group messages by worker
    from collections import defaultdict
    messages_by_worker = defaultdict(list)

    for msg in messages:
        worker_name = msg.get('worker_name', 'Unknown Worker')
        messages_by_worker[worker_name].append(msg)

    # Format messages for prompt - grouped by worker
    conversation_text = ""
    for worker_name, worker_messages in messages_by_worker.items():
        conversation_text += f"\n=== {worker_name.upper()} ===\n"
        
        for msg in worker_messages:
            timestamp = msg.get('timestamp', '')
            if timestamp:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = timestamp[:16] if len(timestamp) >= 16 else timestamp
            else:
                time_str = "Unknown time"
            
            conversation_text += f"[{time_str}] {msg['text']}\n"
    
    # Build prompt - VERY SPECIFIC to avoid summarization
    prompt = f"""You are extracting ACTION ITEMS from a {industry_name} workplace conversation.

CRITICAL INSTRUCTIONS:
1. Do NOT summarize the conversation. Do NOT explain what happened. ONLY extract specific action items.
2. Output your response ONLY in {output_language}. This is mandatory.

Context: {description}

Conversation (last 24 hours):
{conversation_text}

EXTRACTION RULES:
1. Extract ONLY items that require action or follow-up
2. Format as bullet points (use • symbol)
3. Be specific - include details like names, numbers, locations
4. Group under these categories ONLY if items exist:
   - Action Items
   - Safety Issues
   - Equipment

INCLUDE:
- Specific tasks mentioned ("check cow 115", "fix gate in section 3")
- Safety concerns that need addressing
- Equipment problems requiring attention
- Explicit instructions or requests

EXCLUDE:
- Greetings, confirmations, acknowledgments
- Questions that were already answered
- General conversation or updates
- Completed tasks (if marked as done)

OUTPUT FORMAT (in {output_language}):
If action items exist, group them by worker name:

🤖 [WORKER NAME]:
Action Items:
- [specific task with details]

Safety Issues:
- [specific safety concern]

Equipment:
- [specific equipment problem]

🤖 [NEXT WORKER NAME]:
...

Safety Issues:
- [specific safety concern]

Equipment:
- [specific equipment problem]

If NO action items exist:
"No action items found."

REMEMBER: 
- Each bullet point must be a SPECIFIC, ACTIONABLE task - not a summary
- Your ENTIRE response must be in {output_language}"""

    # Use Claude for action items generation (best quality)
    claude_config = config.get('claude', {})
    
    try:
        client = _get_claude_client()
    except ValueError:
        return "Error: Claude API key not configured for action items generation."
    
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
        return f"Error generating action items: {str(e)}"