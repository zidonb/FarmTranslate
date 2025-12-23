import json
import os

def load_config():
    """
    Load configuration from config.json + secrets
    
    Secrets come from:
    - Environment variables (when deployed on Railway)
    - secrets.json (when running locally)
    """
    
    # Load non-secret configuration
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Add secrets from environment (Railway) or secrets.json (local)
    if os.getenv('TELEGRAM_TOKEN'):
        # Running on Railway/cloud - use environment variables
        config['telegram_token'] = os.getenv('TELEGRAM_TOKEN')
        config['claude']['api_key'] = os.getenv('CLAUDE_API_KEY')
        config['gemini']['api_key'] = os.getenv('GEMINI_API_KEY', '')
        config['openai']['api_key'] = os.getenv('OPENAI_API_KEY', '')
        config['lemonsqueezy']['webhook_secret'] = os.getenv('LEMONSQUEEZY_WEBHOOK_SECRET', '')
    else:
        # Running locally - use secrets.json
        try:
            with open('secrets.json', 'r') as f:
                secrets = json.load(f)
            config['telegram_token'] = secrets['telegram_token']
            config['claude']['api_key'] = secrets['claude_api_key']
            config['gemini']['api_key'] = secrets.get('gemini_api_key', '')
            config['openai']['api_key'] = secrets.get('openai_api_key', '')
            config['lemonsqueezy']['webhook_secret'] = secrets.get('lemonsqueezy_webhook_secret', '')
        except FileNotFoundError:
            raise Exception("secrets.json not found! Create it with your API keys.")
    
    return config