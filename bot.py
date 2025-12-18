import json
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
import translator

# Conversation states
LANGUAGE, ROLE, CODE_INPUT = range(3)

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def generate_code():
    """Generate unique farm code"""
    while True:
        code = f"FARM-{random.randint(1000, 9999)}"
        # Check if code already exists
        all_users = database.get_all_users()
        existing_codes = [u.get('code') for u in all_users.values() if u.get('code')]
        if code not in existing_codes:
            return code

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if user:
        await update.message.reply_text(
            f"Welcome back! You're registered as {user['role']}.\n"
            f"Your language: {user['language']}"
        )
        return ConversationHandler.END
    
    # New user - ask for language
    keyboard = [['English', 'Thai'], ['Hebrew', 'Arabic'], ['Spanish', 'Turkish'], ['French', 'German']]
    await update.message.reply_text(
        "Welcome to FarmTranslate! 🚜\n\nSelect your language:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return LANGUAGE

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected language"""
    context.user_data['language'] = update.message.text
    
    keyboard = [['Employer', 'Employee']]
    await update.message.reply_text(
        "Are you an Employer or Employee?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return ROLE

async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected role"""
    user_id = str(update.effective_user.id)
    role = update.message.text.lower()
    language = context.user_data['language']
    
    if role == 'employer':
        code = generate_code()
        user_data = {
            'language': language,
            'role': 'employer',
            'code': code,
            'employees': []
        }
        database.save_user(user_id, user_data)
        
        await update.message.reply_text(
            f"✅ Registered as Employer!\n\n"
            f"📋 Your code: {code}\n\n"
            f"Share this code with your employees so they can connect."
        )
        return ConversationHandler.END
    
    elif role == 'employee':
        context.user_data['role'] = 'employee'
        await update.message.reply_text("Please enter your employer's code (e.g., FARM-1234):")
        return CODE_INPUT
    
    return ConversationHandler.END

async def code_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Employee entered employer code"""
    user_id = str(update.effective_user.id)
    code = update.message.text.strip().upper()
    language = context.user_data['language']
    
    # Find employer with this code
    all_users = database.get_all_users()
    employer_id = None
    
    for uid, udata in all_users.items():
        if udata.get('role') == 'employer' and udata.get('code') == code:
            employer_id = uid
            break
    
    if not employer_id:
        await update.message.reply_text("❌ Invalid code. Please try again or contact your employer.")
        return CODE_INPUT
    
    # Save employee
    employee_data = {
        'language': language,
        'role': 'employee',
        'employer': employer_id
    }
    database.save_user(user_id, employee_data)
    
    # Update employer's employee list
    employer_data = database.get_user(employer_id)
    employer_data['employees'].append(user_id)
    database.save_user(employer_id, employer_data)
    
    await update.message.reply_text("✅ Connected to your employer! You can start chatting now.")
    
    # Notify employer
    employer_name = update.effective_user.first_name
    await context.bot.send_message(
        chat_id=employer_id,
        text=f"✅ {employer_name} connected as your employee!"
    )
    
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages - translate and forward"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    text = update.message.text
    user_lang = user['language']
    
    if user['role'] == 'employer':
    # Send to all employees (silently)
        employer_name = update.effective_user.first_name
        for emp_id in user['employees']:
            employee = database.get_user(emp_id)
            if employee:
                translated = translator.translate(text, user_lang, employee['language'])
                await context.bot.send_message(
                    chat_id=emp_id,
                    text=f"🗣️ From {employer_name}: {translated}"
                )
        # No confirmation message - just silent success
    
    elif user['role'] == 'employee':
        # Send to employer (silently)
        employer_id = user['employer']
        employer = database.get_user(employer_id)
        if employer:
            translated = translator.translate(text, user_lang, employer['language'])
            sender_name = update.effective_user.first_name
            await context.bot.send_message(
                chat_id=employer_id,
                text=f"🗣️ From {sender_name}: {translated}"
            )
        # No confirmation message - just silent success


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("Registration cancelled. Use /start to try again.")
    return ConversationHandler.END

def main():
    """Start the bot"""
    config = load_config()
    app = Application.builder().token(config['telegram_token']).build()
    
    # Conversation handler for registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
            ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, role_selected)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_entered)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 FarmTranslate bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()