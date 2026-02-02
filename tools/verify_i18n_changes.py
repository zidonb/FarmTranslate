"""
Verify i18n changes - shows only content differences, ignoring formatting
"""

import json

LANGUAGES = ['en', 'es', 'he', 'ar', 'th', 'tr', 'fr', 'de', 'pt', 'ru', 'hi', 'tl']

# Keys we expect to have changed
CHANGED_KEYS = [
    'addworker.no_worker_on_current_bot',
    'handle_message.manager.no_worker',
    'handle_task_creation.no_worker',
    'handle_media.manager_no_worker'
]

def get_nested_value(data, key_path):
    """Get value from nested dict using dot notation"""
    keys = key_path.split('.')
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current

def check_file(lang_code):
    """Check what changed in a file"""
    file_path = f'locales/{lang_code}.json'
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n{'='*60}")
        print(f"📄 {lang_code}.json")
        print(f"{'='*60}")
        
        for key_path in CHANGED_KEYS:
            value = get_nested_value(data, key_path)
            if value:
                # Check if /mycode was removed
                has_mycode = '/mycode' in value.lower()
                has_placeholders = '{code}' in value and '{invite_link}' in value
                
                status = "❌ STILL HAS /mycode" if has_mycode else "✅ Fixed"
                placeholder_status = "✅ Has placeholders" if has_placeholders else "⚠️  Missing placeholders"
                
                print(f"\n🔑 {key_path}")
                print(f"   Status: {status}")
                print(f"   Placeholders: {placeholder_status}")
                print(f"   Value: {value[:100]}..." if len(value) > 100 else f"   Value: {value}")
            else:
                print(f"\n🔑 {key_path}")
                print(f"   ❌ KEY NOT FOUND")
        
        return True
        
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return False
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in {file_path}")
        return False

def main():
    """Check all language files"""
    print("🔍 VERIFYING I18N CHANGES")
    print("Checking if /mycode was removed and placeholders added...\n")
    
    for lang_code in LANGUAGES:
        check_file(lang_code)
    
    print(f"\n{'='*60}")
    print("✅ Verification complete!")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()