import json
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
import translator
import conversations
from config import load_config

# Conversation states
LANGUAGE, GENDER, INDUSTRY, CODE_INPUT = range(4)


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
    """User selected gender - now ask for industry"""
    context.user_data['gender'] = update.message.text
    
    # Get industries from config
    config = load_config()
    industries = config.get('industries', {})
    
    # Build keyboard with industry options
    industry_buttons = []
    for key, info in industries.items():
        industry_buttons.append(info['name'])
    
    # Create keyboard (2 per row)
    keyboard = [industry_buttons[i:i+2] for i in range(0, len(industry_buttons), 2)]
    
    await update.message.reply_text(
        "What industry do you work in?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return INDUSTRY

async def industry_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected industry - register as manager"""
    user_id = str(update.effective_user.id)
    language = context.user_data['language']
    gender = context.user_data['gender']
    industry_name = update.message.text
    
    # Find industry key from name
    config = load_config()
    industries = config.get('industries', {})
    industry_key = None
    for key, info in industries.items():
        if info['name'] == industry_name:
            industry_key = key
            break
    
    if not industry_key:
        industry_key = 'other'  # Fallback
    
    # Generate code and register as manager
    code = generate_code()
    user_data = {
        'language': language,
        'gender': gender,
        'role': 'manager',
        'industry': industry_key,
        'code': code,
        'worker': None  # Single worker (None = no worker yet)
    }
    database.save_user(user_id, user_data)
    
    await update.message.reply_text(
        f"✅ Registered as Manager!\n\n"
        f"📋 Your code: {code}\n\n"
        f"Share this code with your worker to connect.\n\n"
        f"Use /help to see available commands.",
        reply_markup=ReplyKeyboardRemove()
    )
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
    
    # Check if manager already has a worker
    manager = database.get_user(manager_id)
    if manager.get('worker'):
        await update.message.reply_text(
            "❌ This manager already has a worker connected.\n"
            "Ask your manager to use /reset first."
        )
        return ConversationHandler.END
    
    # Save worker
    worker_data = {
        'language': language,
        'gender': gender,
        'role': 'worker',
        'manager': manager_id
    }
    database.save_user(user_id, worker_data)
    
    # Update manager's worker
    manager['worker'] = user_id
    database.save_user(manager_id, manager)
    
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
/reset - Delete account and start over

💬 *How to use:*
Just type your message and it will be automatically translated and sent to your worker!
        """
    else:  # worker
        help_text = """
📋 *Available Commands:*

/help - Show this help message
/reset - Delete account

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
    has_worker = user.get('worker') is not None
    
    await update.message.reply_text(
        f"📋 *Your Connection Code:*\n\n"
        f"`{code}`\n\n"
        f"👥 Worker connected: {'Yes' if has_worker else 'No'}\n\n"
        f"Share this code with your worker to connect them.",
        parse_mode='Markdown'
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user account - delete all data and allow re-registration"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("You don't have an account to reset.")
        return
    
    if user['role'] == 'manager':
        # If manager has a worker, delete worker and notify them
        worker_id = user.get('worker')
        if worker_id:
            worker = database.get_user(worker_id)
            if worker:
                # Clear conversation history
                conversations.clear_conversation(user_id, worker_id)
                
                # Delete worker account
                all_users = database.get_all_users()
                if worker_id in all_users:
                    del all_users[worker_id]
                    database.save_data(all_users)
                
                # Notify worker
                try:
                    await context.bot.send_message(
                        chat_id=worker_id,
                        text="⚠️ Your manager has reset their account.\n"
                             "Your account has also been reset.\n\n"
                             "You'll need a new code to reconnect."
                    )
                except Exception:
                    pass
    
    elif user['role'] == 'worker':
        # Remove worker from manager
        manager_id = user.get('manager')
        if manager_id:
            manager = database.get_user(manager_id)
            if manager:
                # Clear manager's worker reference
                manager['worker'] = None
                database.save_user(manager_id, manager)
                
                # Notify manager
                try:
                    worker_name = update.effective_user.first_name
                    await context.bot.send_message(
                        chat_id=manager_id,
                        text=f"ℹ️ {worker_name} has reset their account and is no longer connected."
                    )
                except Exception:
                    pass
            
            # Clear conversation history
            conversations.clear_conversation(user_id, manager_id)
    
    # Delete user data
    all_users = database.get_all_users()
    if user_id in all_users:
        del all_users[user_id]
        database.save_data(all_users)
    
    await update.message.reply_text(
        "✅ Your account has been reset!\n\n"
        "All your data and connections have been deleted.\n"
        "Use /start to register again."
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
    history_size = config.get('history_size', 5)
    max_history_messages = history_size * 2  # per side
    
    if user['role'] == 'manager':
        # Check if manager has a worker
        worker_id = user.get('worker')
        if not worker_id:
            await update.message.reply_text(
                "⚠️ You don't have a worker connected yet.\n"
                "Share your code (use /mycode) with your worker."
            )
            return
        
        worker = database.get_user(worker_id)
        if not worker:
            await update.message.reply_text(
                "⚠️ Your worker's account no longer exists.\n"
                "Use /reset to start over."
            )
            return
        
        # Get conversation history
        history = conversations.get_conversation_history(user_id, worker_id, max_history_messages)
        
        # Get manager's industry for context
        industry_key = user.get('industry', 'other')
        
        # Translate with context
        translated = translator.translate(
            text=text,
            from_lang=user_lang,
            to_lang=worker['language'],
            target_gender=worker.get('gender'),
            conversation_history=history,
            industry=industry_key
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
        manager_name = update.effective_user.first_name
        await context.bot.send_message(
            chat_id=worker_id,
            text=f"🗣️ From {manager_name}: {translated}"
        )
    
    elif user['role'] == 'worker':
        # Send to manager
        manager_id = user.get('manager')
        if not manager_id:
            await update.message.reply_text(
                "⚠️ You're not connected to a manager.\n"
                "Ask your manager for their code and use /start."
            )
            return
        
        manager = database.get_user(manager_id)
        if not manager:
            await update.message.reply_text(
                "⚠️ Your manager's account no longer exists.\n"
                "Use /reset and wait for a new code."
            )
            return
        
        # Get conversation history
        history = conversations.get_conversation_history(user_id, manager_id, max_history_messages)
        
        # Get manager's industry for context
        industry_key = manager.get('industry', 'other')
        
        # Translate with context
        translated = translator.translate(
            text=text,
            from_lang=user_lang,
            to_lang=manager['language'],
            target_gender=manager.get('gender'),
            conversation_history=history,
            industry=industry_key
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
            INDUSTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, industry_selected)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_entered)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('mycode', mycode_command))
    app.add_handler(CommandHandler('reset', reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 FarmTranslate bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()