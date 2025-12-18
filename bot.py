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
    
    keyboard = [['Manager', 'Worker']]
    await update.message.reply_text(
        "Are you a Manager or Worker?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return ROLE

async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected role"""
    user_id = str(update.effective_user.id)
    role = update.message.text.lower()
    language = context.user_data['language']
    
    if role == 'manager':
        code = generate_code()
        user_data = {
            'language': language,
            'role': 'manager',
            'code': code,
            'workers': []
        }
        database.save_user(user_id, user_data)
        
        await update.message.reply_text(
            f"✅ Registered as Manager!\n\n"
            f"📋 Your code: {code}\n\n"
            f"Share this code with your workers so they can connect."
        )
        return ConversationHandler.END
    
    elif role == 'worker':
        context.user_data['role'] = 'worker'
        await update.message.reply_text("Please enter your manager's code (e.g., FARM-1234):")
        return CODE_INPUT
    
    return ConversationHandler.END

async def code_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Worker entered manager code"""
    user_id = str(update.effective_user.id)
    code = update.message.text.strip().upper()
    language = context.user_data['language']
    
    # Find manager with this code
    all_users = database.get_all_users()
    manager_id = None
    
    for uid, udata in all_users.items():
        if udata.get('role') == 'manager' and udata.get('code') == code:
            manager_id = uid
            break
    
    if not manager_id:
        await update.message.reply_text("❌ Invalid code. Please try again or contact your manager.")
        return CODE_INPUT
    
    # Save worker
    worker_data = {
        'language': language,
        'role': 'worker',
        'manager': manager_id
    }
    database.save_user(user_id, worker_data)
    
    # Update manager's worker list
    manager_data = database.get_user(manager_id)
    manager_data['workers'].append(user_id)
    database.save_user(manager_id, manager_data)
    
    await update.message.reply_text("✅ Connected to your manager! You can start chatting now.")
    
    # Notify manager
    worker_name = update.effective_user.first_name
    await context.bot.send_message(
        chat_id=manager_id,
        text=f"✅ {worker_name} connected as your worker!"
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
    
    if user['role'] == 'manager':
        # Send to all workers (silently)
        manager_name = update.effective_user.first_name
        for worker_id in user['workers']:
            worker = database.get_user(worker_id)
            if worker:
                translated = translator.translate(text, user_lang, worker['language'])
                await context.bot.send_message(
                    chat_id=worker_id,
                    text=f"🗣️ From {manager_name}: {translated}"
                )
    
    elif user['role'] == 'worker':
        # Send to manager (silently)
        manager_id = user['manager']
        manager = database.get_user(manager_id)
        if manager:
            translated = translator.translate(text, user_lang, manager['language'])
            sender_name = update.effective_user.first_name
            await context.bot.send_message(
                chat_id=manager_id,
                text=f"🗣️ From {sender_name}: {translated}"
            )

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