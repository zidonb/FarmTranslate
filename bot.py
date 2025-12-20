import json
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
import translator
import conversations
from config import load_config

# Conversation states
LANGUAGE, GENDER, ROLE, CODE_INPUT = range(4)


def generate_code():
    """Generate unique code"""
    while True:
        code = f"FARM-{random.randint(1000, 9999)}"
        # Check if code already exists
        all_users = database.get_all_users()
        existing_codes = [u.get('code') for u in all_users.values() if u.get('code')]
        if code not in existing_codes:
            return code

# ============================================
# REGISTRATION COMMANDS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if user:
        await update.message.reply_text(
            f"Welcome back! You're registered as {user['role']}.\n"
            f"Your language: {user['language']}\n\n"
            f"Use /help to see available commands."
        )
        return ConversationHandler.END
    
    # New user - ask for language
    # Get languages from config
    config = load_config()
    available_languages = config.get('languages', ['English', 'Spanish'])
    
    # Build keyboard dynamically (2 languages per row)
    keyboard = [available_languages[i:i+2] for i in range(0, len(available_languages), 2)]
    
    await update.message.reply_text(
        "Welcome to FarmTranslate! 🚜\n\nSelect your language:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return LANGUAGE

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected language"""
    context.user_data['language'] = update.message.text
    
    keyboard = [['Male', 'Female'], ['Prefer not to say']]
    await update.message.reply_text(
        "What is your gender?\n(This helps with accurate translations)",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return GENDER

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected gender"""
    context.user_data['gender'] = update.message.text
    
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
    gender = context.user_data['gender']
    
    if role == 'manager':
        code = generate_code()
        user_data = {
            'language': language,
            'gender': gender,
            'role': 'manager',
            'code': code,
            'workers': []
        }
        database.save_user(user_id, user_data)
        
        await update.message.reply_text(
            f"✅ Registered as Manager!\n\n"
            f"📋 Your code: {code}\n\n"
            f"Share this code with your workers so they can connect.\n\n"
            f"Use /help to see available commands.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    elif role == 'worker':
        context.user_data['role'] = 'worker'
        await update.message.reply_text(
            "Please enter your manager's code (e.g., FARM-1234):",
            reply_markup=ReplyKeyboardRemove()
        )
        return CODE_INPUT
    
    return ConversationHandler.END

async def code_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Worker entered manager code"""
    user_id = str(update.effective_user.id)
    code = update.message.text.strip().upper()
    language = context.user_data['language']
    gender = context.user_data['gender']
    
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
        'gender': gender,
        'role': 'worker',
        'manager': manager_id
    }
    database.save_user(user_id, worker_data)
    
    # Update manager's worker list
    manager_data = database.get_user(manager_id)
    manager_data['workers'].append(user_id)
    database.save_user(manager_id, manager_data)
    
    await update.message.reply_text(
        "✅ Connected to your manager! You can start chatting now.\n\n"
        "Use /help to see available commands."
    )
    
    # Notify manager
    worker_name = update.effective_user.first_name
    await context.bot.send_message(
        chat_id=manager_id,
        text=f"✅ {worker_name} connected as your worker!"
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text(
        "Registration cancelled. Use /start to try again.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ============================================
# USER COMMANDS
# ============================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available commands"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text(
            "Please use /start to register first."
        )
        return
    
    if user['role'] == 'manager':
        help_text = """
📋 *Available Commands:*

/help - Show this help message
/mycode - Show your connection code
/start - Re-register (if needed)

💬 *How to use:*
Just type your message and it will be automatically translated and sent to your workers!
        """
    else:  # worker
        help_text = """
📋 *Available Commands:*

/help - Show this help message
/start - Re-register (if needed)

💬 *How to use:*
Just type your message and it will be automatically translated and sent to your manager!
        """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def mycode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show manager's code"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    if user['role'] != 'manager':
        await update.message.reply_text("Only managers have connection codes.")
        return
    
    code = user.get('code', 'No code found')
    worker_count = len(user.get('workers', []))
    
    await update.message.reply_text(
        f"📋 *Your Connection Code:*\n\n"
        f"`{code}`\n\n"
        f"👥 Connected workers: {worker_count}\n\n"
        f"Share this code with your workers to connect them.",
        parse_mode='Markdown'
    )

# ============================================
# MESSAGE HANDLING
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages - translate and forward"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    text = update.message.text
    user_lang = user['language']
    
    # Get history size from config
    config = load_config()
    history_size = config.get('context', {}).get('history_size', 5)
    max_history_messages = history_size * 2  # 5 per side = 10 total
    
    if user['role'] == 'manager':
        # Send to all workers
        manager_name = update.effective_user.first_name
        for worker_id in user['workers']:
            worker = database.get_user(worker_id)
            if worker:
                # Get conversation history
                history = conversations.get_conversation_history(user_id, worker_id, max_history_messages)
                
                # Translate with context
                translated = translator.translate(
                    text=text,
                    from_lang=user_lang,
                    to_lang=worker['language'],
                    target_gender=worker.get('gender'),
                    conversation_history=history
                )
                
                # Save message to history
                conversations.add_to_conversation(
                    user_id_1=user_id,
                    user_id_2=worker_id,
                    from_id=user_id,
                    text=text,
                    language=user_lang,
                    max_history=max_history_messages
                )
                
                # Send translated message
                await context.bot.send_message(
                    chat_id=worker_id,
                    text=f"🗣️ From {manager_name}: {translated}"
                )
    
    elif user['role'] == 'worker':
        # Send to manager
        manager_id = user['manager']
        manager = database.get_user(manager_id)
        if manager:
            # Get conversation history
            history = conversations.get_conversation_history(user_id, manager_id, max_history_messages)
            
            # Translate with context
            translated = translator.translate(
                text=text,
                from_lang=user_lang,
                to_lang=manager['language'],
                target_gender=manager.get('gender'),
                conversation_history=history
            )
            
            # Save message to history
            conversations.add_to_conversation(
                user_id_1=user_id,
                user_id_2=manager_id,
                from_id=user_id,
                text=text,
                language=user_lang,
                max_history=max_history_messages
            )
            
            # Send translated message
            sender_name = update.effective_user.first_name
            await context.bot.send_message(
                chat_id=manager_id,
                text=f"🗣️ From {sender_name}: {translated}"
            )

# ============================================
# MAIN APPLICATION
# ============================================

def main():
    """Start the bot"""
    config = load_config()
    app = Application.builder().token(config['telegram_token']).build()
    
    # Conversation handler for registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_selected)],
            ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, role_selected)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_entered)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('mycode', mycode_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 FarmTranslate bot is running...")
    print("📋 Context: " + config.get('context', {}).get('industry', 'Not set'))
    app.run_polling()

if __name__ == '__main__':
    main()