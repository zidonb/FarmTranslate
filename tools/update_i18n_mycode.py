"""
One-time script to remove /mycode references from all i18n files
Run once: python update_i18n_mycode.py
"""

import json
import os

# New translations for each key
UPDATES = {
    "addworker.no_worker_on_current_bot": {
        "en": "⚠️ Please connect a worker to this bot first.\n\nShare your invitation with your first worker:\n\n📋 Code: {code}\n🔗 Link: {invite_link}",
        "es": "⚠️ Por favor conecta un trabajador a este bot primero.\n\nComparte tu invitación con tu primer trabajador:\n\n📋 Código: {code}\n🔗 Enlace: {invite_link}",
        "he": "⚠️ אנא חבר עובד לבוט הזה תחילה.\n\nשתף את ההזמנה שלך עם העובד הראשון שלך:\n\n📋 קוד: {code}\n🔗 קישור: {invite_link}",
        "ar": "⚠️ يرجى ربط عامل بهذا البوت أولاً.\n\nشارك دعوتك مع عاملك الأول:\n\n📋 الرمز: {code}\n🔗 الرابط: {invite_link}",
        "th": "⚠️ กรุณาเชื่อมต่อพนักงานกับบอทนี้ก่อน\n\nแชร์คำเชิญของคุณกับพนักงานคนแรก:\n\n📋 รหัส: {code}\n🔗 ลิงก์: {invite_link}",
        "tr": "⚠️ Lütfen önce bu bota bir çalışan bağlayın.\n\nİlk çalışanınızla davetinizi paylaşın:\n\n📋 Kod: {code}\n🔗 Bağlantı: {invite_link}",
        "fr": "⚠️ Veuillez d'abord connecter un travailleur à ce bot.\n\nPartagez votre invitation avec votre premier travailleur:\n\n📋 Code: {code}\n🔗 Lien: {invite_link}",
        "de": "⚠️ Bitte verbinden Sie zuerst einen Arbeiter mit diesem Bot.\n\nTeilen Sie Ihre Einladung mit Ihrem ersten Arbeiter:\n\n📋 Code: {code}\n🔗 Link: {invite_link}",
        "pt": "⚠️ Por favor, conecte um trabalhador a este bot primeiro.\n\nCompartilhe seu convite com seu primeiro trabalhador:\n\n📋 Código: {code}\n🔗 Link: {invite_link}",
        "ru": "⚠️ Пожалуйста, сначала подключите работника к этому боту.\n\nПоделитесь приглашением с вашим первым работником:\n\n📋 Код: {code}\n🔗 Ссылка: {invite_link}",
        "hi": "⚠️ कृपया पहले इस बॉट से एक कार्यकर्ता को कनेक्ट करें।\n\nअपने पहले कार्यकर्ता के साथ अपना निमंत्रण साझा करें:\n\n📋 कोड: {code}\n🔗 लिंक: {invite_link}",
        "tl": "⚠️ Mangyaring ikonekta muna ang isang manggagawa sa bot na ito.\n\nIbahagi ang iyong imbitasyon sa iyong unang manggagawa:\n\n📋 Code: {code}\n🔗 Link: {invite_link}"
    },
    "handle_message.manager.no_worker": {
        "en": "⚠️ You don't have a worker connected to this bot yet.\n\nShare your invitation to connect a worker:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "es": "⚠️ Aún no tienes un trabajador conectado a este bot.\n\nComparte tu invitación para conectar un trabajador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "he": "⚠️ עדיין אין לך עובד מחובר לבוט הזה.\n\nשתף את ההזמנה שלך כדי לחבר עובד:\n\n📋 קוד: {code}\n🔗 {invite_link}",
        "ar": "⚠️ ليس لديك عامل متصل بهذا البوت بعد.\n\nشارك دعوتك لربط عامل:\n\n📋 الرمز: {code}\n🔗 {invite_link}",
        "th": "⚠️ คุณยังไม่มีพนักงานเชื่อมต่อกับบอทนี้\n\nแชร์คำเชิญของคุณเพื่อเชื่อมต่อพนักงาน:\n\n📋 รหัส: {code}\n🔗 {invite_link}",
        "tr": "⚠️ Bu bota henüz bağlı çalışanınız yok.\n\nBir çalışan bağlamak için davetinizi paylaşın:\n\n📋 Kod: {code}\n🔗 {invite_link}",
        "fr": "⚠️ Vous n'avez pas encore de travailleur connecté à ce bot.\n\nPartagez votre invitation pour connecter un travailleur:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "de": "⚠️ Sie haben noch keinen Arbeiter mit diesem Bot verbunden.\n\nTeilen Sie Ihre Einladung, um einen Arbeiter zu verbinden:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "pt": "⚠️ Você ainda não tem um trabalhador conectado a este bot.\n\nCompartilhe seu convite para conectar um trabalhador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "ru": "⚠️ У вас еще нет работника, подключенного к этому боту.\n\nПоделитесь приглашением, чтобы подключить работника:\n\n📋 Код: {code}\n🔗 {invite_link}",
        "hi": "⚠️ आपके पास अभी तक इस बॉट से जुड़ा कोई कार्यकर्ता नहीं है।\n\nकार्यकर्ता को कनेक्ट करने के लिए अपना निमंत्रण साझा करें:\n\n📋 कोड: {code}\n🔗 {invite_link}",
        "tl": "⚠️ Wala ka pang manggagawa na nakakonekta sa bot na ito.\n\nIbahagi ang iyong imbitasyon upang kumonekta ng manggagawa:\n\n📋 Code: {code}\n🔗 {invite_link}"
    },
    "handle_task_creation.no_worker": {
        "en": "⚠️ You don't have a worker connected to this bot yet.\n\nShare your invitation to connect a worker:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "es": "⚠️ Aún no tienes un trabajador conectado a este bot.\n\nComparte tu invitación para conectar un trabajador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "he": "⚠️ עדיין אין לך עובד מחובר לבוט הזה.\n\nשתף את ההזמנה שלך כדי לחבר עובד:\n\n📋 קוד: {code}\n🔗 {invite_link}",
        "ar": "⚠️ ليس لديك عامل متصل بهذا البوت بعد.\n\nشارك دعوتك لربط عامل:\n\n📋 الرمز: {code}\n🔗 {invite_link}",
        "th": "⚠️ คุณยังไม่มีพนักงานเชื่อมต่อกับบอทนี้\n\nแชร์คำเชิญของคุณเพื่อเชื่อมต่อพนักงาน:\n\n📋 รหัส: {code}\n🔗 {invite_link}",
        "tr": "⚠️ Bu bota henüz bağlı çalışanınız yok.\n\nBir çalışan bağlamak için davetinizi paylaşın:\n\n📋 Kod: {code}\n🔗 {invite_link}",
        "fr": "⚠️ Vous n'avez pas encore de travailleur connecté à ce bot.\n\nPartagez votre invitation pour connecter un travailleur:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "de": "⚠️ Sie haben noch keinen Arbeiter mit diesem Bot verbunden.\n\nTeilen Sie Ihre Einladung, um einen Arbeiter zu verbinden:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "pt": "⚠️ Você ainda não tem um trabalhador conectado a este bot.\n\nCompartilhe seu convite para conectar um trabalhador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "ru": "⚠️ У вас еще нет работника, подключенного к этому боту.\n\nПоделитесь приглашением, чтобы подключить работника:\n\n📋 Код: {code}\n🔗 {invite_link}",
        "hi": "⚠️ आपके पास अभी तक इस बॉट से जुड़ा कोई कार्यकर्ता नहीं है।\n\nकार्यकर्ता को कनेक्ट करने के लिए अपना निमंत्रण साझा करें:\n\n📋 कोड: {code}\n🔗 {invite_link}",
        "tl": "⚠️ Wala ka pang manggagawa na nakakonekta sa bot na ito.\n\nIbahagi ang iyong imbitasyon upang kumonekta ng manggagawa:\n\n📋 Code: {code}\n🔗 {invite_link}"
    },
    "handle_media.manager_no_worker": {
        "en": "⚠️ You don't have a worker connected to this bot yet.\n\nShare your invitation to connect a worker:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "es": "⚠️ Aún no tienes un trabajador conectado a este bot.\n\nComparte tu invitación para conectar un trabajador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "he": "⚠️ עדיין אין לך עובד מחובר לבוט הזה.\n\nשתף את ההזמנה שלך כדי לחבר עובד:\n\n📋 קוד: {code}\n🔗 {invite_link}",
        "ar": "⚠️ ليس لديك عامل متصل بهذا البوت بعد.\n\nشارك دعوتك لربط عامل:\n\n📋 الرمز: {code}\n🔗 {invite_link}",
        "th": "⚠️ คุณยังไม่มีพนักงานเชื่อมต่อกับบอทนี้\n\nแชร์คำเชิญของคุณเพื่อเชื่อมต่อพนักงาน:\n\n📋 รหัส: {code}\n🔗 {invite_link}",
        "tr": "⚠️ Bu bota henüz bağlı çalışanınız yok.\n\nBir çalışan bağlamak için davetinizi paylaşın:\n\n📋 Kod: {code}\n🔗 {invite_link}",
        "fr": "⚠️ Vous n'avez pas encore de travailleur connecté à ce bot.\n\nPartagez votre invitation pour connecter un travailleur:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "de": "⚠️ Sie haben noch keinen Arbeiter mit diesem Bot verbunden.\n\nTeilen Sie Ihre Einladung, um einen Arbeiter zu verbinden:\n\n📋 Code: {code}\n🔗 {invite_link}",
        "pt": "⚠️ Você ainda não tem um trabalhador conectado a este bot.\n\nCompartilhe seu convite para conectar um trabalhador:\n\n📋 Código: {code}\n🔗 {invite_link}",
        "ru": "⚠️ У вас еще нет работника, подключенного к этому боту.\n\nПоделитесь приглашением, чтобы подключить работника:\n\n📋 Код: {code}\n🔗 {invite_link}",
        "hi": "⚠️ आपके पास अभी तक इस बॉट से जुड़ा कोई कार्यकर्ता नहीं है।\n\nकार्यकर्ता को कनेक्ट करने के लिए अपना निमंत्रण साझा करें:\n\n📋 कोड: {code}\n🔗 {invite_link}",
        "tl": "⚠️ Wala ka pang manggagawa na nakakonekta sa bot na ito.\n\nIbahagi ang iyong imbitasyon upang kumonekta ng manggagawa:\n\n📋 Code: {code}\n🔗 {invite_link}"
    }
}

LANGUAGES = ['en', 'es', 'he', 'ar', 'th', 'tr', 'fr', 'de', 'pt', 'ru', 'hi', 'tl']

def set_nested_key(data, key_path, value):
    """Set a value in nested dict using dot notation"""
    keys = key_path.split('.')
    current = data
    
    # Navigate to the parent
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the final value
    current[keys[-1]] = value

def update_language_file(lang_code):
    """Update a single language file"""
    file_path = f'locales/{lang_code}.json'
    
    # Load existing file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  File not found: {file_path}")
        return False
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in {file_path}")
        return False
    
    # Update each key
    updated_count = 0
    for key_path, translations in UPDATES.items():
        if lang_code in translations:
            set_nested_key(data, key_path, translations[lang_code])
            updated_count += 1
    
    # Save file with proper formatting
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Updated {file_path} ({updated_count} keys)")
    return True

def main():
    """Update all language files"""
    print("🔄 Starting i18n updates (removing /mycode references)...\n")
    
    success_count = 0
    fail_count = 0
    
    for lang_code in LANGUAGES:
        if update_language_file(lang_code):
            success_count += 1
        else:
            fail_count += 1
    
    print(f"\n{'='*50}")
    print(f"✅ Successfully updated: {success_count} files")
    if fail_count > 0:
        print(f"❌ Failed: {fail_count} files")
    print(f"{'='*50}")
    
    if fail_count == 0:
        print("\n🎉 All i18n files updated successfully!")
        print("📝 Don't forget to update bot.py as well (4 locations)")
    else:
        print("\n⚠️  Some files failed to update. Please check the errors above.")

if __name__ == '__main__':
    main()