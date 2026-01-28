import os
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import database
import translator
import translation_msg_context
import message_history
import usage_tracker
import subscription_manager
from config import load_config
import feedback
import tasks 
from datetime import datetime, timezone
import json
from i18n import get_text
import db_connection 
from collections import defaultdict

# Conversation states
LANGUAGE, GENDER, INDUSTRY = range(3)


def generate_code():
    """Generate unique code"""
    while True:
        code = f"BRIDGE-{random.randint(10000, 99999)}"
        # Check if code already exists
        all_users = database.get_all_users()
        existing_codes = [u.get('code') for u in all_users.values() if u.get('code')]
        if code not in existing_codes:
            return code

# ============================================
# REGISTRATION COMMANDS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with optional deep-link parameter"""
    print(f"📥 /start command received from user {update.effective_user.id}")
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    # Check if user already registered
    if user:
        welcome_text = get_text(
        user['language'],
        'start.welcome_back',
        default="Welcome back! You're registered as {role}.\n\nUse /help to see available commands.",
        role=user['role']
    )
        await update.message.reply_text(welcome_text)
        return ConversationHandler.END
    
    # Clear any existing conversation state to allow clean restart
    context.user_data.clear()
    
    # Check for deep-link parameter (e.g., /start invite_FARM-1234)
    if context.args and len(context.args) > 0:
        param = context.args[0]
        if param.startswith('invite_'):
            code = param.replace('invite_', '')
            # Store code in context for later use
            context.user_data['invite_code'] = code
    
    # New user - ask for language
    config = load_config()
    available_languages = config.get('languages', ['English', 'Spanish'])
    
    # Build keyboard dynamically (2 languages per row)
    keyboard = [available_languages[i:i+2] for i in range(0, len(available_languages), 2)]
    
    welcome_new_text = get_text(
        'English',  # Default to English for new users who haven't selected language yet
        'start.welcome_new',
        default="Welcome to BridgeOS! 🌉\n\nSelect your language:"
    )
    
    await update.message.reply_text(
        welcome_new_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return LANGUAGE

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected language"""
    selected_language = update.message.text
    context.user_data['language'] = selected_language
    
    # Get translated gender question
    gender_question = get_text(
        selected_language,
        'registration.gender_question',
        default="What is your gender?\n(This helps with accurate translations)"
    )
    
    # Get translated gender options
    male = get_text(selected_language, 'registration.gender_options.male', default="Male")
    female = get_text(selected_language, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(selected_language, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")
    
    keyboard = [[male, female], [prefer_not]]
    await update.message.reply_text(
        gender_question,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return GENDER

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected gender - check if they have an invite code or ask for industry"""
    
    # Get user's selected language
    language = context.user_data['language']
    
    # Get the SAME translated gender options we showed in language_selected()
    male = get_text(language, 'registration.gender_options.male', default="Male")
    female = get_text(language, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(language, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")
    
    # Create reverse mapping: translated text → English
    gender_reverse_map = {
        male: 'Male',
        female: 'Female',
        prefer_not: 'Prefer not to say'
    }
    
    # Convert tapped button (in user's language) to English
    english_gender = gender_reverse_map.get(update.message.text, 'Prefer not to say')
    
    # Save ENGLISH version (what translator.py expects)
    context.user_data['gender'] = english_gender
    
    # Check if user came via deep-link with invite code
    if 'invite_code' in context.user_data:
        code = context.user_data['invite_code']
        user_id = str(update.effective_user.id)
        gender = context.user_data['gender']  # Now in English
        
        # Find manager with this code
        all_users = database.get_all_users()
        manager_id = None
        
        for uid, udata in all_users.items():
            if udata.get('role') == 'manager' and udata.get('code') == code:
                manager_id = uid
                break
        
        if not manager_id:
            invalid_code_text = get_text(
                language,
                'registration.invalid_code',
                default="❌ Invalid invitation code.\n\nPlease ask your contact for a new invitation link."
            )
            await update.message.reply_text(
                invalid_code_text,
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Check if manager already has a worker on THIS bot
        manager = database.get_user(manager_id)
        bot_id = os.environ.get('BOT_ID', 'bot1')
        workers = manager.get('workers', [])

        # Check if this bot already has a worker for this manager
        worker_on_this_bot = next((w for w in workers if w.get('bot_id') == bot_id), None)

        if worker_on_this_bot:
            already_connected_text = get_text(
                language,
                'registration.worker_already_connected',
                default="❌ This contact already has a worker connected on this bot.\nAsk them to use /reset first."
            )
            await update.message.reply_text(
                already_connected_text,
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # ✅ BUG FIX: Check if this worker is switching from another manager
        existing_worker = database.get_user(user_id)
        if existing_worker and existing_worker.get('manager'):
            old_manager_id = existing_worker['manager']
            if old_manager_id != manager_id:  # Switching to a different manager
                # Clean up old manager's stale reference
                old_manager = database.get_user(old_manager_id)
                if old_manager and old_manager.get('worker') == user_id:
                    old_manager['worker'] = None
                    database.save_user(old_manager_id, old_manager)
                    print(f"✅ Cleaned up old manager {old_manager_id} reference to worker {user_id}")
                    
                    # Notify old manager that worker disconnected
                    try:
                        worker_name = update.effective_user.first_name or "Your worker"
                        manager_notification_text = get_text(
                            old_manager['language'],
                            'registration.worker_switched',
                            default="⚠️ {worker_name} has connected to a different manager.\n\nYou can now invite a new worker using /mycode",
                            worker_name=worker_name
                        )
                        await context.bot.send_message(
                            chat_id=old_manager_id,
                            text=manager_notification_text
                        )
                    except Exception as e:
                        print(f"Could not notify old manager: {e}")
        
        # Save worker
        worker_data = {
            'language': language,
            'gender': gender,  # English gender (e.g., "Male")
            'role': 'worker',
            'manager': manager_id,
            'bot_id': os.environ.get('BOT_ID', 'bot1')
        }
        database.save_user(user_id, worker_data)
        
        # Update manager's workers array
        if 'workers' not in manager:
            manager['workers'] = []  # Initialize if old data format

        manager['workers'].append({
            'worker_id': user_id,
            'bot_id': os.environ.get('BOT_ID', 'bot1'),
            'status': 'active',
            'registered_at': datetime.now(timezone.utc).isoformat()
        })
        database.save_user(manager_id, manager)
        
        connection_success_text = get_text(
            language,
            'registration.connection_success',
            default="✅ Connected to your contact! You can start chatting now.\n\nUse /help to see available commands."
        )
        await update.message.reply_text(
            connection_success_text,
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Notify manager
        worker_name = update.effective_user.first_name
        manager_notification_text = get_text(
            manager['language'],  # Use manager's language for notification
            'registration.manager_notification',
            default="✅ {worker_name} connected as your worker!",
            worker_name=worker_name
        )
        await context.bot.send_message(
            chat_id=manager_id,
            text=manager_notification_text
        )
        
        return ConversationHandler.END
    
    # No invite code - user is registering as manager
    # Ask for industry
    config = load_config()
    industries = config.get('industries', {})

    industry_buttons = []
    for key in industries.keys():
        # ✅ Get translated industry name based on user's language
        translated_name = get_text(
            language,
            f'industries.{key}',
            default=industries[key]['name']
        )
        industry_buttons.append(translated_name)

    keyboard = [industry_buttons[i:i+2] for i in range(0, len(industry_buttons), 2)]

    industry_question_text = get_text(
        language,
        'registration.industry_question',
        default="What industry do you work in?\n\nThis helps provide accurate translations of technical terms and workplace-specific language."
    )

    await update.message.reply_text(
        industry_question_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return INDUSTRY

async def industry_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected industry - register as manager"""
    user_id = str(update.effective_user.id)
    language = context.user_data['language']
    gender = context.user_data['gender']
    industry_name = update.message.text  # User tapped button (e.g., "🐄 רפת")
    
    # Find industry key from name
    config = load_config()
    industries = config.get('industries', {})
    
    # ✅ NEW: Build reverse mapping (translated name → English key)
    industry_reverse_map = {}
    for key in industries.keys():
        translated_name = get_text(
            language,
            f'industries.{key}',
            default=industries[key]['name']
        )
        industry_reverse_map[translated_name] = key
    
    # ✅ NEW: Use reverse map to get English key
    industry_key = industry_reverse_map.get(industry_name, 'other')
    
    # Generate code and register as manager
    code = generate_code()
    user_data = {
        'language': language,
        'gender': gender,
        'role': 'manager',
        'industry': industry_key,
        'code': code,
        'workers': []
    }
    database.save_user(user_id, user_data)
    
    # Create deep-link for invitation
    bot_username = "FarmTranslateBot"  # Your bot username
    deep_link = f"https://t.me/{bot_username}?start=invite_{code}"
    
    # Create share button with prefilled message
    share_text = get_text(
        language,
        'registration.share_invitation_text',
        default="🌉 Join BridgeOS!\nChat with me in your language:\n{deep_link}",
        deep_link=deep_link
    )
    
    share_button_text = get_text(
        language,
        'registration.share_invitation_button',
        default="🚀 Send Invitation Now"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(share_button_text, switch_inline_query=share_text)]
    ])
    
    # Send invitation message with share button
    registration_complete_text = get_text(
        language,
        'registration.registration_complete',
        default="✅ Registration complete!\n\n📋 Your invitation code: {code}\n🔗 Invitation link:\n{deep_link}\n\n👉 Tap the button below to share with your contact:",
        code=code,
        deep_link=deep_link
    )
    
    await update.message.reply_text(
        registration_complete_text,
        reply_markup=keyboard
    )

    ready_text = get_text(
        language,
        'registration.ready_to_start',
        default="Ready to start! Use /help anytime."
    )
    
    await update.message.reply_text(
        ready_text,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    # Try to get user's language from context, fallback to English
    language = context.user_data.get('language', 'English')
    
    cancelled_text = get_text(
        language,
        'registration.cancelled',
        default="Registration cancelled. Use /start to try again."
    )
    
    await update.message.reply_text(
        cancelled_text,
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
        not_registered_text = get_text(
            'English',  # Default to English for non-registered users
            'help.not_registered',
            default="Please use /start to register first."
        )
        await update.message.reply_text(not_registered_text)
        return
    
    language = user['language']
    
    if user['role'] == 'manager':
        help_text = get_text(
            language,
            'help.manager_commands',
            default="📋 *Available Commands:*\n\n/help - Show this help message\n/tasks - View your task list\n/daily - Get daily action items\n/subscription - View subscription status\n/reset - Delete account and start over\n/mycode - Show your connection code\n/refer - Recommend to other managers\n/feedback - Send feedback to BridgeOS team\n\n💬 *How to use:*\nJust type your message and it will be automatically translated and sent to your contact!"
        )
    else:
        help_text = get_text(
            language,
            'help.worker_commands',
            default="📋 *Available Commands:*\n\n/help - Show this help message\n/tasks - View your task list\n/refer - Recommend to other managers\n/feedback - Send feedback to BridgeOS team\n/reset - Delete account\n\n💬 *How to use:*\nJust type your message and it will be automatically translated and sent to your contact!"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show role-aware menu with localized buttons"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        not_registered_text = get_text(
            'English',
            'menu.not_registered',
            default="Please use /start to register first."
        )
        await update.message.reply_text(not_registered_text)
        return
    
    language = user['language']
    
    # Build buttons based on role
    if user['role'] == 'manager':
        keyboard = [
            [InlineKeyboardButton(get_text(language, 'menu.tasks', default='📋 My Tasks'), callback_data='menu_tasks')],
            [InlineKeyboardButton(get_text(language, 'menu.daily', default='📊 Daily Action Items'), callback_data='menu_daily')],
            [InlineKeyboardButton(get_text(language, 'menu.addworker', default='➕ Add Worker'), callback_data='menu_addworker')],
            [InlineKeyboardButton(get_text(language, 'menu.mycode', default='🔗 My Invitation Code'), callback_data='menu_mycode')],
            [InlineKeyboardButton(get_text(language, 'menu.subscription', default='💳 Subscription'), callback_data='menu_subscription')],
            [InlineKeyboardButton(get_text(language, 'menu.refer', default='📤 Refer BridgeOS'), callback_data='menu_refer')],
            [InlineKeyboardButton(get_text(language, 'menu.feedback', default='💬 Send Feedback'), callback_data='menu_feedback')],
            [InlineKeyboardButton(get_text(language, 'menu.reset', default='🗑️ Reset Account'), callback_data='menu_reset')]
        ]
    else:  # worker
        keyboard = [
            [InlineKeyboardButton(get_text(language, 'menu.tasks', default='📋 My Tasks'), callback_data='menu_tasks')],
            [InlineKeyboardButton(get_text(language, 'menu.refer', default='📤 Refer BridgeOS'), callback_data='menu_refer')],
            [InlineKeyboardButton(get_text(language, 'menu.feedback', default='💬 Send Feedback'), callback_data='menu_feedback')],
            [InlineKeyboardButton(get_text(language, 'menu.reset', default='🗑️ Reset Account'), callback_data='menu_reset')]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        get_text(language, 'menu.title', default='📋 BridgeOS Menu\n\nSelect an option:'),
        reply_markup=reply_markup
    )

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu button presses"""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    
    # Route to appropriate command
    if query.data == 'menu_tasks':
        await tasks_command(update, context)
    elif query.data == 'menu_daily':
        await daily_command(update, context)
    elif query.data == 'menu_addworker':  # ← ADD THIS
        await addworker_command(update, context)
    elif query.data == 'menu_mycode':
        await mycode_command(update, context)
    elif query.data == 'menu_subscription':
        await subscription_command(update, context)
    elif query.data == 'menu_refer':
        await refer_command(update, context)
    elif query.data == 'menu_feedback':
        await feedback_command(update, context)
    elif query.data == 'menu_reset':
        await reset(update, context)

async def mycode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show manager's code with share button"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        not_registered_text = get_text(
            'English',
            'mycode.not_registered',
            default="Please use /start to register first."
        )
        await send_message(not_registered_text)
        return
    
    language = user['language']
    
    if user['role'] != 'manager':
        not_manager_text = get_text(
            language,
            'mycode.not_manager',
            default="Only managers have connection codes."
        )
        await send_message(not_manager_text)
        return
    
    code = user.get('code', 'No code found')
    workers = user.get('workers', [])
    has_workers = len(workers) > 0
    
    # Create deep-link for invitation
    bot_username = "FarmTranslateBot"  # Your bot username
    deep_link = f"https://t.me/{bot_username}?start=invite_{code}"
    
    # Create share button with prefilled message
    share_text = get_text(
        language,
        'registration.share_invitation_text',  # Reuse from registration
        default="🌉 Join BridgeOS!\nChat with me in your language:\n{deep_link}",
        deep_link=deep_link
    )
    
    share_button_text = get_text(
        language,
        'mycode.share_button',
        default="📤 Share Invitation"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(share_button_text, switch_inline_query=share_text)]
    ])
    
    # Get status text
    # Build workers list
    workers_list = ""
    if has_workers:
        for idx, worker_data in enumerate(workers, 1):
            bot_id = worker_data.get('bot_id', 'unknown')
            worker_id = worker_data.get('worker_id', 'unknown')
            status = worker_data.get('status', 'unknown')
            workers_list += f"\n{idx}. Bot {bot_id}: Worker {worker_id} ({status})"
    else:
        workers_list = "\nNo workers connected yet"

    # Send status and invitation
    status_text = get_text(
        language,
        'mycode.status',
        default="👥 Your Workers:{workers_list}\n\n📋 Your invitation code: {code}\n🔗 Invitation link:\n{deep_link}\n\n👉 Tap the button below to share with your contact:",
        workers_list=workers_list,
        code=code,
        deep_link=deep_link
    )
    
    await send_message(
        status_text,
        reply_markup=keyboard
    )

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let users share the bot with other managers/colleagues"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    # Get user's language, fallback to English if not registered
    language = user['language'] if user else 'English'
    
    # Load config for dynamic language count
    config = load_config()
    language_count = len(config.get('languages', []))
    
    # Shareable message for other potential managers
    share_text = get_text(
        language,
        'refer.share_text',
        default="🌉 Check out BridgeOS!\n\nI use it to communicate with my team in real-time - we speak different languages but chat naturally!\n\n🌍 {language_count} languages supported\n✅ Instant translation\n🏭 Industry-specific terms\n💬 Simple & effective\n\nTry it free: https://t.me/FarmTranslateBot",
        language_count=language_count
    )
    
    button_text = get_text(
        language,
        'refer.button',
        default="📤 Recommend BridgeOS"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, switch_inline_query=share_text)]
    ])
    
    message_text = get_text(
        language,
        'refer.message',
        default="🌉 Love BridgeOS?\n\nHelp other managers break language barriers!\n\nRecommend BridgeOS to colleagues, friends, or anyone who manages teams speaking different languages.\n\n👉 Tap the button to share:"
    )
    
    await send_message(
        message_text,
        reply_markup=keyboard
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user account - delete all data and allow re-registration"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        no_account_text = get_text(
            'English',  # Default to English for non-registered users
            'reset.no_account',
            default="You don't have an account to reset."
        )
        await send_message(no_account_text)
        return
    
    language = user['language']
    
    if user['role'] == 'manager':
        workers = user.get('workers', [])
        
        # Delete all workers and clear conversations
        for worker_data in workers:
            worker_id = worker_data.get('worker_id')
            if worker_id:
                worker = database.get_user(worker_id)
                if worker:
                    translation_msg_context.clear_conversation(user_id, worker_id)
                    
                    all_users = database.get_all_users()
                    if worker_id in all_users:
                        del all_users[worker_id]
                        database.save_data(all_users)
                
                try:
                    worker_notification_text = get_text(
                        worker['language'],  # Use worker's language
                        'reset.worker_notification',
                        default="⚠️ Your contact has reset their account.\nYour account has also been reset.\n\nYou'll need a new invitation to reconnect."
                    )
                    await context.bot.send_message(
                        chat_id=worker_id,
                        text=worker_notification_text
                    )
                except Exception:
                    pass
    
    elif user['role'] == 'worker':
        manager_id = user.get('manager')
        if manager_id:
            manager = database.get_user(manager_id)
            if manager:
                # Remove this worker from manager's workers array
                workers = manager.get('workers', [])
                manager['workers'] = [w for w in workers if w.get('worker_id') != user_id]
                database.save_user(manager_id, manager)
                
                try:
                    worker_name = update.effective_user.first_name if not update.callback_query else update.callback_query.from_user.first_name
                    manager_notification_text = get_text(
                        manager['language'],  # Use manager's language
                        'reset.manager_notification',
                        default="ℹ️ {worker_name} has reset their account and is no longer connected.",
                        worker_name=worker_name
                    )
                    await context.bot.send_message(
                        chat_id=manager_id,
                        text=manager_notification_text
                    )
                except Exception:
                    pass
            
            translation_msg_context.clear_conversation(user_id, manager_id)
    
    all_users = database.get_all_users()
    if user_id in all_users:
        del all_users[user_id]
        database.save_data(all_users)
    
    success_text = get_text(
        language,
        'reset.success',
        default="✅ Your account has been reset!\n\nAll your data and connections have been deleted.\nUse /start to register again."
    )
    
    await send_message(success_text)

    
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI-powered Action items of last 24 hours"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        not_registered_text = get_text(
            'English',
            'daily.not_registered',
            default="Please use /start to register first."
        )
        await send_message(not_registered_text)
        return
    
    language = user['language']
    
    # Only managers can get summaries
    if user['role'] != 'manager':
        not_manager_text = get_text(
            language,
            'daily.not_manager',
            default="Only managers can generate summaries.\n\nThis feature helps managers track action items and tasks."
        )
        await send_message(not_manager_text)
        return
    
    # Check if manager has any workers
    workers = user.get('workers', [])
    if not workers:
        no_worker_text = get_text(
            language,
            'daily.no_worker',
            default="You don't have a worker connected yet.\n\nConnect with a worker first to see conversation summaries."
        )
        await send_message(no_worker_text)
        return
    
    # Send "generating" message
    generating_text = get_text(
        language,
        'daily.generating',
        default="⏳ Generating Daily Action Items (Last 24 Hours)...\n\nAnalyzing last 24 hours of conversation."
    )
    generating_msg = await send_message(generating_text)
    
    try:
        # Get messages from last 24 hours - ALL WORKERS with names
        all_messages = []
        worker_info = {}  # Map worker_id to worker name
        
        for worker_data in workers:
            worker_id = worker_data.get('worker_id')
            bot_id = worker_data.get('bot_id', 'unknown')
            
            if worker_id:
                # Get worker's Telegram info for their name
                try:
                    worker_user = await context.bot.get_chat(worker_id)
                    worker_name = worker_user.first_name or f"Bot {bot_id}"
                except Exception:
                    worker_name = f"Bot {bot_id}"  # Fallback if can't fetch
                
                messages = message_history.get_messages(
                    user_id_1=user_id,
                    user_id_2=worker_id,
                    hours=24
                )
                
                # Tag each message with worker name
                for msg in messages:
                    msg['worker_name'] = worker_name
                
                all_messages.extend(messages)
                worker_info[worker_id] = worker_name
        
        messages = all_messages
            
        # Get industry context
        industry_key = user.get('industry', 'other')
        
        # Generate daily action items using Claude
        action_items_text = translator.generate_daily_actionitems(messages, industry=industry_key, manager_language=user['language'])
        
        # Count total messages
        message_count = len(messages)
        
        # Format response
        response = get_text(
            language,
            'daily.result_header',
            default="📋 *Daily Action Items (Last 24 Hours)*\n\n{action_items}",
            action_items=action_items_text
        )
        
        # Add message count if there are messages
        if message_count > 0:
            message_count_text = get_text(
                language,
                'daily.message_count',
                default="\n\n_Total messages: {count}_",
                count=message_count
            )
            response += message_count_text
        
        # Delete "generating" message
        await generating_msg.delete()
        
        # Send daily action items
        await send_message(response, parse_mode='Markdown')
        
    except Exception as e:
        # Delete "generating" message
        await generating_msg.delete()
        
        # Send error message
        error_text = get_text(
            language,
            'daily.error',
            default="❌ Error generating daily action items: {error}\n\nPlease try again later or contact support.",
            error=str(e)
        )
        await send_message(error_text)

async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription status and management"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        not_registered_text = get_text(
            'English',
            'subscription.not_registered',
            default="Please use /start to register first."
        )
        await send_message(not_registered_text)
        return
    
    language = user['language']
    
    if user['role'] != 'manager':
        worker_unlimited_text = get_text(
            language,
            'subscription.worker_unlimited',
            default="Workers have unlimited messages! 🎉\n\nOnly managers need subscriptions."
        )
        await send_message(
            worker_unlimited_text,
            parse_mode='Markdown'
        )
        return
    
    # Load config for pricing
    config = load_config()
    monthly_price = config.get('lemonsqueezy', {}).get('monthly_price', 9.00)
    free_limit = config.get('free_message_limit', 50)
    
    # Get subscription status
    subscription = subscription_manager.get_subscription(user_id)
    
    if not subscription or subscription.get('status') in ['expired', None]:
        # No subscription or expired - show subscribe option
        checkout_url = subscription_manager.create_checkout_url(user_id)
        usage = usage_tracker.get_usage(user_id)
        messages_sent = usage.get('messages_sent', 0)
        
        button_text = get_text(
            language,
            'subscription.no_subscription.button',
            default="🏢 Upgrade to Business License (${price}/month)",
            price=f"{monthly_price:.0f}"
        )
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(button_text, url=checkout_url)
        ]])
        
        # Build message parts
        title = get_text(language, 'subscription.no_subscription.title', default="📋 *Subscription Status*\n\n")
        status = get_text(language, 'subscription.no_subscription.status', default="Status: ❌ No Active Subscription\n")
        usage_text = get_text(
            language,
            'subscription.no_subscription.usage',
            default="Messages Used: {messages_sent} / {free_limit} (Free Tier)\n\n",
            messages_sent=messages_sent,
            free_limit=free_limit
        )
        benefits_header = get_text(language, 'subscription.no_subscription.benefits_header', default="💳 *Subscribe to BridgeOS:*\n")
        benefits = get_text(
            language,
            'subscription.no_subscription.benefits',
            default="• Unlimited messages\n• ${price}/month\n• Cancel anytime",
            price=f"{monthly_price:.0f}"
        )
        
        message = title + status + usage_text + benefits_header + benefits
        
        await send_message(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        # Has subscription - show details
        status = subscription.get('status', 'unknown')
        renews_at = subscription.get('renews_at', 'N/A')[:10] if subscription.get('renews_at') else 'N/A'
        ends_at = subscription.get('ends_at')
        portal_url = subscription.get('customer_portal_url')
        
        # Status emoji
        status_emoji = {
            'active': '✅',
            'cancelled': '⚠️',
            'paused': '⏸️',
            'expired': '❌'
        }.get(status, '❓')
        
        # Build message parts
        title = get_text(language, 'subscription.active_subscription.title', default="📋 *Your Subscription*\n\n")
        status_text = get_text(
            language,
            'subscription.active_subscription.status',
            default="{emoji} Status: {status}\n",
            emoji=status_emoji,
            status=status.title()
        )
        plan = get_text(language, 'subscription.active_subscription.plan', default="💳 Plan: Unlimited Messages\n")
        price = get_text(
            language,
            'subscription.active_subscription.price',
            default="💵 Price: ${price}/month\n",
            price=f"{monthly_price:.0f}"
        )
        
        message = title + status_text + plan + price
        
        if status == 'active':
            renews = get_text(
                language,
                'subscription.active_subscription.renews',
                default="📅 Renews: {date}\n",
                date=renews_at
            )
            message += renews
        elif status == 'cancelled' and ends_at:
            access_until = get_text(
                language,
                'subscription.active_subscription.access_until',
                default="📅 Access Until: {date}\n",
                date=ends_at[:10]
            )
            message += access_until
        
        footer = get_text(language, 'subscription.active_subscription.footer', default="\n_Manage or cancel anytime._")
        message += footer
        
        if portal_url:
            manage_button_text = get_text(
                language,
                'subscription.active_subscription.manage_button',
                default="⚙️ Manage Business License"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(manage_button_text, url=portal_url)
            ]])
            await send_message(message, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await send_message(message, parse_mode='Markdown')

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task list for manager or worker"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        not_registered_text = get_text(
            'English',
            'tasks.not_registered',
            default="Please use /start to register first."
        )
        await send_message(not_registered_text)
        return
    
    language = user['language']
    
    if user['role'] == 'manager':
        # Get manager's tasks
        pending_tasks = tasks.get_manager_tasks(user_id, status='pending')
        completed_tasks = tasks.get_manager_tasks(user_id, status='completed', limit_hours=24)
        
        if not pending_tasks and not completed_tasks:
            title = get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n")
            no_tasks = get_text(
                language,
                'tasks.manager.no_tasks',
                default="No tasks yet.\n\nCreate a task by sending a message starting with **\nExample: ** Check cow 115 for heat"
            )
            await send_message(
                title + no_tasks,
                parse_mode='Markdown'
            )
            return
        
        # Format response
        response = get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n")
        
        # Pending tasks - grouped by worker
        if pending_tasks:
            pending_header = get_text(
                language,
                'tasks.manager.pending_header',
                default="⏳ *PENDING ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                count=len(pending_tasks)
            )
            response += pending_header
            
            # Group tasks by worker
            from collections import defaultdict
            tasks_by_worker = defaultdict(list)
            
            for task in pending_tasks:
                worker_id = task.get('worker_id')
                tasks_by_worker[worker_id].append(task)
            
            # Display each worker's tasks
            for worker_id, worker_tasks in tasks_by_worker.items():
                # Get worker name from Telegram
                try:
                    worker_user = await context.bot.get_chat(worker_id)
                    worker_name = worker_user.first_name or f"Worker {worker_id}"
                except Exception:
                    worker_name = f"Worker {worker_id}"
                
                response += f"\n👤 *{worker_name}:*\n"
                
                for task in worker_tasks:
                    created_time = task['created_at'].strftime('%H:%M') if task.get('created_at') else 'Unknown'
                    task_item = get_text(
                        language,
                        'tasks.manager.task_item',
                        default="• {description}\n  _Created: Today at {time}_\n\n",
                        description=task['description'],
                        time=created_time
                    )
                    response += task_item
        
        # Completed tasks (today only) - grouped by worker
        if completed_tasks:
            completed_header = get_text(
                language,
                'tasks.manager.completed_header',
                default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                count=len(completed_tasks)
            )
            response += completed_header
            
            # Group tasks by worker
            completed_by_worker = defaultdict(list)
            
            for task in completed_tasks:
                worker_id = task.get('worker_id')
                completed_by_worker[worker_id].append(task)
            
            # Display each worker's completed tasks
            for worker_id, worker_tasks in completed_by_worker.items():
                # Get worker name from Telegram
                try:
                    worker_user = await context.bot.get_chat(worker_id)
                    worker_name = worker_user.first_name or f"Worker {worker_id}"
                except Exception:
                    worker_name = f"Worker {worker_id}"
                
                response += f"\n👤 *{worker_name}:*\n"
                
                for task in worker_tasks:
                    completed_time = task['completed_at'].strftime('%H:%M') if task.get('completed_at') else 'Unknown'
                    completed_item = get_text(
                        language,
                        'tasks.manager.completed_item',
                        default="• {description}\n  _Completed at {time}_\n\n",
                        description=task['description'],
                        time=completed_time
                    )
                    response += completed_item
        
        await send_message(response, parse_mode='Markdown')
    
    elif user['role'] == 'worker':
        # Get worker's tasks
        pending_tasks = tasks.get_worker_tasks(user_id, status='pending')
        completed_tasks = tasks.get_worker_tasks(user_id, status='completed', limit_hours=24)
        
        if not pending_tasks and not completed_tasks:
            title = get_text(language, 'tasks.worker.title', default="📋 *Your Tasks*\n\n")
            no_tasks = get_text(
                language,
                'tasks.worker.no_tasks',
                default="No tasks assigned yet.\n\nYour manager will send you tasks when needed."
            )
            await send_message(
                title + no_tasks,
                parse_mode='Markdown'
            )
            return
        
        # Format response
        response = get_text(language, 'tasks.worker.title', default="📋 *Your Tasks*\n\n")
        
        # Pending tasks
        if pending_tasks:
            todo_header = get_text(
                language,
                'tasks.worker.todo_header',
                default="⏳ *TO DO ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                count=len(pending_tasks)
            )
            response += todo_header
            
            for task in pending_tasks:
                task_item = get_text(
                    language,
                    'tasks.worker.task_item',
                    default="• {description}\n\n",
                    description=task['description']
                )
                response += task_item
            
            instruction = get_text(
                language,
                'tasks.worker.instruction',
                default="_Tap the ✅ Mark Done button on each task message to complete it._\n\n"
            )
            response += instruction
        
        # Completed tasks (today only)
        if completed_tasks:
            completed_header = get_text(
                language,
                'tasks.worker.completed_header',
                default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                count=len(completed_tasks)
            )
            response += completed_header
            
            for task in completed_tasks:
                completed_item = get_text(
                    language,
                    'tasks.worker.completed_item',
                    default="• {description} ✓\n",
                    description=task['description']
                )
                response += completed_item
        
        await send_message(response, parse_mode='Markdown')
        
async def view_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'View All Tasks' button click from task creation confirmation"""
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    # Answer the callback immediately
    await query.answer()
    
    user = database.get_user(user_id)
    
    if not user or user['role'] != 'manager':
        not_manager_text = get_text(
            user['language'] if user else 'English',
            'view_tasks_callback.not_manager',
            default="⚠️ Only managers can view tasks."
        )
        await query.edit_message_text(not_manager_text)
        return
    
    language = user['language']
    
    # Get manager's tasks
    pending_tasks = tasks.get_manager_tasks(user_id, status='pending')
    completed_tasks = tasks.get_manager_tasks(user_id, status='completed', limit_hours=24)
    
    if not pending_tasks and not completed_tasks:
        no_other_tasks = get_text(
            language,
            'view_tasks_callback.no_other_tasks',
            default="📋 *Your Tasks*\n\nNo other tasks yet.\n\nCreate more tasks by sending messages starting with **"
        )
        await query.edit_message_text(
            no_other_tasks,
            parse_mode='Markdown'
        )
        return
    
    # Format response (same as tasks_command)
    response = get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n")
    
    if pending_tasks:
        pending_header = get_text(
            language,
            'tasks.manager.pending_header',
            default="⏳ *PENDING ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
            count=len(pending_tasks)
        )
        response += pending_header
        
        for task in pending_tasks:
            created_time = task['created_at'].strftime('%H:%M') if task.get('created_at') else 'Unknown'
            task_item = get_text(
                language,
                'tasks.manager.task_item',
                default="• {description}\n  _Created: Today at {created_time}_\n\n",
                description=task['description'],
                created_time=created_time
            )
            response += task_item
    
    if completed_tasks:
        completed_header = get_text(
            language,
            'tasks.manager.completed_header',
            default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n",
            count=len(completed_tasks)
        )
        response += completed_header
        
        for task in completed_tasks:
            completed_time = task['completed_at'].strftime('%H:%M') if task.get('completed_at') else 'Unknown'
            completed_item = get_text(
                language,
                'tasks.manager.completed_item',
                default="• {description}\n  _Completed at {completed_time}_\n\n",
                description=task['description'],
                completed_time=completed_time
            )
            response += completed_item
    
    await query.edit_message_text(response, parse_mode='Markdown')

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feedback command - collect user feedback"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    # Get user's language, fallback to English if not registered
    language = user['language'] if user else 'English'
    
    # Set flag to capture next message as feedback
    context.user_data['awaiting_feedback'] = True
    
    prompt_text = get_text(
        language,
        'feedback.prompt',
        default="💡 *Send Your Feedback*\n\nType your message below and I'll forward it to the BridgeOS team.\n\nShare suggestions, report bugs, or tell us what you think!"
    )
    
    await send_message(
        prompt_text,
        parse_mode='Markdown'
    )


async def addworker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new worker - find free bot and send proactive invite"""
    # Handle both direct command AND callback from menu
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        user = database.get_user(user_id)
        send_message = update.callback_query.message.reply_text
    else:
        user_id = str(update.effective_user.id)
        user = database.get_user(user_id)
        send_message = update.message.reply_text
    
    if not user:
        not_registered_text = get_text(
            'English',
            'addworker.not_registered',
            default="Please use /start to register first."
        )
        await send_message(not_registered_text)
        return
    
    language = user['language']
    
    # Only managers can add workers
    if user['role'] != 'manager':
        not_manager_text = get_text(
            language,
            'addworker.not_manager',
            default="⚠️ Only managers can add workers.\n\nWorkers are added by their managers."
        )
        await send_message(not_manager_text)
        return
    
    # Check worker limit
    max_workers = 5
    current_workers = user.get('workers', [])
    
    if len(current_workers) >= max_workers:
        limit_reached_text = get_text(
            language,
            'addworker.limit_reached',
            default="⚠️ *Worker Limit Reached*\n\nYou already have {count} workers (maximum allowed).\n\nTo add another worker, please contact support for enterprise options.",
            count=len(current_workers)
        )
        await send_message(
            limit_reached_text,
            parse_mode='Markdown'
        )
        return
    
    # Find which bots this manager already uses
    available_bot_ids = ['bot1', 'bot2', 'bot3', 'bot4', 'bot5']
    used_bot_ids = [w.get('bot_id') for w in current_workers]
    free_bot_ids = [b for b in available_bot_ids if b not in used_bot_ids]
    
    if not free_bot_ids:
        all_bots_used_text = get_text(
            language,
            'addworker.all_bots_used',
            default="⚠️ All bot slots are in use.\n\nYou have workers on all 5 bots. This shouldn't happen - please contact support."
        )
        await send_message(all_bots_used_text)
        return
    
    # Get the next free bot
    next_bot_id = free_bot_ids[0]
    
    # Get manager's code
    code = user.get('code', 'No code found')
    
    # Bot username mapping
    bot_usernames = {
        'bot1': 'FarmTranslateBot',
        'bot2': 'BridgeOS_2bot',
        'bot3': 'BridgeOS_3bot',
        'bot4': 'BridgeOS_4bot',
        'bot5': 'BridgeOS_5bot'
    }
    
    bot_username = bot_usernames.get(next_bot_id, 'FarmTranslateBot')
    
    # Create links
    bot_chat_link = f"https://t.me/{bot_username}"
    invite_link = f"https://t.me/{bot_username}?start=invite_{code}"
    
    # Get bot token for the next bot (to send proactive message)
    bot_tokens = {
    'bot1': os.environ.get('TELEGRAM_TOKEN_BOT1'),  # ✅ Always read from shared variables
    'bot2': os.environ.get('TELEGRAM_TOKEN_BOT2'),
    'bot3': os.environ.get('TELEGRAM_TOKEN_BOT3'),
    'bot4': os.environ.get('TELEGRAM_TOKEN_BOT4'),
    'bot5': os.environ.get('TELEGRAM_TOKEN_BOT5')
}
    
    next_bot_token = bot_tokens.get(next_bot_id)
    
    # Send proactive message from the next bot
    if next_bot_token:
        try:
            from telegram import Bot
            next_bot = Bot(token=next_bot_token)
            
            # Create share button
            share_text = get_text(
                language,
                'addworker.share_invitation_text',
                default="🌉 Join BridgeOS!\nChat with me in your language:\n{invite_link}",
                invite_link=invite_link
            )
            
            share_button_text = get_text(
                language,
                'addworker.share_button',
                default="🚀 Share Invitation"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(share_button_text, switch_inline_query=share_text)]
            ])
            
            # Greeting message
            greeting_text = get_text(
                language,
                'addworker.bot_greeting',
                default="👋 *Ready to add a worker!*\n\n📋 Share this invitation with your worker:\n\n👉 Tap the button below to share:"
            )
            
            await next_bot.send_message(
                chat_id=user_id,
                text=greeting_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            print(f"Error sending proactive message from {next_bot_id}: {e}")
    
    # Send instructions in current bot
    success_text = get_text(
        language,
        'addworker.success',
        default="✅ *Worker Slot Assigned on {bot_name}*\n\n📱 Open this bot to add your worker:\n{bot_link}\n\n💡 The invitation is waiting for you there!",
        bot_name=next_bot_id.upper(),
        bot_link=bot_chat_link
    )
    
    await send_message(
        success_text,
        parse_mode='Markdown'
    )

# ============================================
# MESSAGE HANDLING
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages - translate and forward, or create tasks"""
    user_id = str(update.effective_user.id)
    
    # Check if user is sending feedback
    if context.user_data.get('awaiting_feedback'):
        # Clear the flag first
        context.user_data['awaiting_feedback'] = False
        
        # Get admin ID from config
        config = load_config()
        admin_id = config.get('admin_telegram_id')
        
        # Get user for language
        user = database.get_user(user_id)
        language = user['language'] if user else 'English'
        
        if not admin_id:
            admin_error_text = get_text(
                language,
                'feedback_handling.admin_error',
                default="⚠️ Error: Admin not configured. Please contact support."
            )
            await update.message.reply_text(admin_error_text)
            return
        
        # Get user info for the feedback message
        user_name = update.effective_user.first_name or "Unknown"
        username = update.effective_user.username
        text = update.message.text
        
        # Format feedback message (admin always gets English)
        feedback_msg = f"💬 *Feedback from {user_name}*\n"
        if username:
            feedback_msg += f"@{username} "
        feedback_msg += f"(ID: {user_id})\n\n{text}"
        
        # Forward to admin
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=feedback_msg,
                parse_mode='Markdown'
            )
            
            # Save to database
            feedback.save_feedback(
                telegram_user_id=user_id,
                user_name=user_name,
                username=username,
                message=text
            )
            
            success_text = get_text(
                language,
                'feedback_handling.success',
                default="✅ *Feedback Sent!*\n\nThank you for sharing your thoughts with us. We read every message and truly appreciate your input!"
            )
            await update.message.reply_text(
                success_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error sending feedback: {e}")
            error_text = get_text(
                language,
                'feedback_handling.error',
                default="⚠️ Sorry, there was an error sending your feedback. Please try again later."
            )
            await update.message.reply_text(error_text)
        
        return
    
    user = database.get_user(user_id)
    
    if not user:
        not_registered_text = get_text(
            'English',
            'handle_message.not_registered',
            default="Please use /start to register first."
        )
        await update.message.reply_text(not_registered_text)
        return
    
    language = user['language']
    text = update.message.text
    
    # Check if it's a task (** prefix at beginning)
    if text.startswith('**'):
        await handle_task_creation(update, context)
        return
    
    # Load config for limits and pricing
    config = load_config()
    free_limit = config.get('free_message_limit', 50)
    monthly_price = config.get('lemonsqueezy', {}).get('monthly_price', 9.00)
    
    # Check message limits (only for managers)
    telegram_id = str(update.effective_user.id)
    if user['role'] == 'manager':
        # Check if user has active subscription
        if subscription_manager.is_subscribed(telegram_id):
            # User has subscription - unlimited messages, skip limit check
            pass
        else:
            # No subscription - check free tier limits
            if usage_tracker.is_user_blocked(telegram_id):
                # Generate subscribe button
                checkout_url = subscription_manager.create_checkout_url(telegram_id)
                
                button_text = get_text(
                    language,
                    'handle_message.limit_reached.button',
                    default="💳 Upgrade to Business License (${price}/month)",
                    price=f"{monthly_price:.0f}"
                )
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(button_text, url=checkout_url)
                ]])
                
                # Build message parts
                title = get_text(language, 'handle_message.limit_reached.title', default="⚠️ *Free Plan Limit Reached*\n\n")
                message_text = get_text(
                    language,
                    'handle_message.limit_reached.message',
                    default="Your business has used its allocation of {free_limit} translated messages.\nTo continue operations without interruption, please upgrade your account to the *Business License*.\n\n",
                    free_limit=free_limit
                )
                benefits_header = get_text(language, 'handle_message.limit_reached.benefits_header', default="*BridgeOS Business License:*\n")
                benefits = get_text(
                    language,
                    'handle_message.limit_reached.benefits',
                    default="✅ Full Business Access (Unlimited usage)\n✅ Manager Dashboard\n✅ Priority Processing\n✅ Industry-Specific Translations\n✅ Multi-Language Support (12 languages)\n• *Price:* ${price}/month (Cancel anytime)\n\n",
                    price=f"{monthly_price:.0f}"
                )
                cta = get_text(language, 'handle_message.limit_reached.cta', default="Tap below to upgrade:")
                
                full_message = title + message_text + benefits_header + benefits + cta
                
                await update.message.reply_text(
                    full_message,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                return
    
    user_lang = user['language']
    
    translation_context_size = config.get('translation_context_size', 5)
    max_history_messages = translation_context_size * 2
    
    if user['role'] == 'manager':
        # Find worker connected to THIS bot
        bot_id = os.environ.get('BOT_ID', 'bot1')
        workers = user.get('workers', [])
        
        # Find worker on this bot
        worker_on_this_bot = next((w for w in workers if w.get('bot_id') == bot_id), None)
        
        if not worker_on_this_bot:
            no_worker_text = get_text(
                language,
                'handle_message.manager.no_worker',
                default="⚠️ You don't have a contact connected yet.\nShare your invitation (use /mycode) with your contact."
            )
            await update.message.reply_text(no_worker_text)
            return
        
        worker_id = worker_on_this_bot.get('worker_id')    
        worker = database.get_user(worker_id)
        if not worker:
            worker_not_found_text = get_text(
                language,
                'handle_message.manager.worker_not_found',
                default="⚠️ Your contact's account no longer exists.\nUse /reset to start over."
            )
            await update.message.reply_text(worker_not_found_text)
            return
        
        history = translation_msg_context.get_conversation_history(user_id, worker_id, max_history_messages)
        industry_key = user.get('industry', 'other')
        
        translated = translator.translate(
            text=text,
            from_lang=user_lang,
            to_lang=worker['language'],
            target_gender=worker.get('gender'),
            conversation_history=history,
            industry=industry_key
        )
        
        translation_msg_context.add_to_conversation(
            user_id_1=user_id,
            user_id_2=worker_id,
            from_id=user_id,
            text=text,
            language=user_lang,
            max_history=max_history_messages
        )
        
        # Also save to message_history for summaries (full 30-day retention)
        message_history.save_message(
            user_id_1=user_id,
            user_id_2=worker_id,
            from_id=user_id,
            text=text,
            language=user_lang
        )
        
        manager_name = update.effective_user.first_name
        
        # Send to worker in worker's language
        message_prefix = get_text(
            worker['language'],  # Worker's language
            'handle_message.manager.message_prefix',
            default="🗣️ From {name}: {translated}",
            name=manager_name,
            translated=translated
        )
        
        await context.bot.send_message(
            chat_id=worker_id,
            text=message_prefix
        )
        
        # Increment message counter for manager (after successful send)
        # Only increment if user doesn't have subscription
        if not subscription_manager.is_subscribed(telegram_id):
            allowed = usage_tracker.increment_message_count(telegram_id)
            
            if not allowed:
                # Just hit the limit - show subscribe button
                checkout_url = subscription_manager.create_checkout_url(telegram_id)
                
                last_message_button = get_text(
                    language,
                    'handle_message.manager.last_message_button',
                    default="🏢 Upgrade to Business License (${price}/month)",
                    price=f"{monthly_price:.0f}"
                )
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(last_message_button, url=checkout_url)
                ]])
                
                last_message_text = get_text(
                    language,
                    'handle_message.manager.last_message',
                    default="⚠️ *That was your last free message!*\n\nYou've used all {free_limit} free messages.\n\n💳 Subscribe for unlimited messages (${price}/month):",
                    free_limit=free_limit,
                    price=f"{monthly_price:.0f}"
                )
                
                await update.message.reply_text(
                    last_message_text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
    
    elif user['role'] == 'worker':
        manager_id = user.get('manager')
        if not manager_id:
            no_manager_text = get_text(
                language,
                'handle_message.worker.no_manager',
                default="⚠️ You're not connected to a contact.\nAsk your contact for their invitation link."
            )
            await update.message.reply_text(no_manager_text)
            return
        
        manager = database.get_user(manager_id)
        if not manager:
            manager_not_found_text = get_text(
                language,
                'handle_message.worker.manager_not_found',
                default="⚠️ Your contact's account no longer exists.\nUse /reset and wait for a new invitation."
            )
            await update.message.reply_text(manager_not_found_text)
            return
        
        history = translation_msg_context.get_conversation_history(user_id, manager_id, max_history_messages)
        industry_key = manager.get('industry', 'other')
        
        translated = translator.translate(
            text=text,
            from_lang=user_lang,
            to_lang=manager['language'],
            target_gender=manager.get('gender'),
            conversation_history=history,
            industry=industry_key
        )
        
        translation_msg_context.add_to_conversation(
            user_id_1=user_id,
            user_id_2=manager_id,
            from_id=user_id,
            text=text,
            language=user_lang,
            max_history=max_history_messages
        )
        
        # Also save to message_history for summaries (full 30-day retention)
        message_history.save_message(
            user_id_1=user_id,
            user_id_2=manager_id,
            from_id=user_id,
            text=text,
            language=user_lang
        )
        
        sender_name = update.effective_user.first_name
        
        # Send to manager in manager's language
        message_prefix = get_text(
            manager['language'],  # Manager's language
            'handle_message.worker.message_prefix',
            default="🗣️ From {name}: {translated}",
            name=sender_name,
            translated=translated
        )
        
        await context.bot.send_message(
            chat_id=manager_id,
            text=message_prefix
        )

async def handle_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task creation when manager sends ** prefix"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    text = update.message.text
    
    language = user['language']
    
    # Only managers can create tasks
    if user['role'] != 'manager':
        not_manager_text = get_text(
            language,
            'handle_task_creation.not_manager',
            default="⚠️ Only managers can create tasks.\nTo send a regular message, don't use **"
        )
        await update.message.reply_text(not_manager_text)
        return
    
    # Find worker connected to THIS bot
    bot_id = os.environ.get('BOT_ID', 'bot1')
    workers = user.get('workers', [])

    worker_on_this_bot = next((w for w in workers if w.get('bot_id') == bot_id), None)

    if not worker_on_this_bot:
        no_worker_text = get_text(
            language,
            'handle_task_creation.no_worker',
            default="⚠️ You don't have a worker connected yet.\nShare your invitation (use /mycode) with your worker first."
        )
        await update.message.reply_text(no_worker_text)
        return

    worker_id = worker_on_this_bot.get('worker_id')  # ✅ ADD THIS LINE

    # Extract task description (remove ** prefix)
    task_description = text[2:].strip()
    
    # Validate not empty
    if not task_description:
        empty_description_text = get_text(
            language,
            'handle_task_creation.empty_description',
            default="⚠️ Please provide a task description after **\n\nExample: ** Check cow 115 for heat"
        )
        await update.message.reply_text(empty_description_text)
        return
    
    # Get worker data
    worker = database.get_user(worker_id)
    if not worker:
        worker_not_found_text = get_text(
            language,
            'handle_task_creation.worker_not_found',
            default="⚠️ Your worker's account no longer exists.\nUse /reset to start over."
        )
        await update.message.reply_text(worker_not_found_text)
        return
    
    # Translate task to worker's language
    try:
        translated_task = translator.translate(
            text=task_description,
            from_lang=user['language'],
            to_lang=worker['language'],
            target_gender=worker.get('gender'),
            industry=user.get('industry')
        )
    except Exception as e:
        print(f"Error translating task: {e}")
        translation_error_text = get_text(
            language,
            'handle_task_creation.translation_error',
            default="⚠️ Error translating task: {error}\nPlease try again.",
            error=str(e)
        )
        await update.message.reply_text(translation_error_text)
        return
    
    # Save task to database
    try:
        task_id = tasks.create_task(
            manager_id=user_id,
            worker_id=worker_id,
            description=task_description,
            description_translated=translated_task
        )
    except Exception as e:
        print(f"Error creating task: {e}")
        creation_error_text = get_text(
            language,
            'handle_task_creation.creation_error',
            default="⚠️ Error creating task: {error}\nPlease try again.",
            error=str(e)
        )
        await update.message.reply_text(creation_error_text)
        return
    
    # Send to worker with checkbox button
    mark_done_button_text = get_text(
        worker['language'],  # Worker's language for button
        'handle_task_creation.mark_done_button',
        default="✅ Mark Done"
    )
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(mark_done_button_text, callback_data=f"task_done_{task_id}")
    ]])
    
    manager_name = update.effective_user.first_name or "Manager"
    
    try:
        worker_task_text = get_text(
            worker['language'],  # Worker's language for task message
            'handle_task_creation.worker_task',
            default="📋 *Task from {manager_name}:*\n{task}",
            manager_name=manager_name,
            task=translated_task
        )
        await context.bot.send_message(
            chat_id=worker_id,
            text=worker_task_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error sending task to worker: {e}")
        send_error_text = get_text(
            language,
            'handle_task_creation.send_error',
            default="⚠️ Error sending task to worker: {error}",
            error=str(e)
        )
        await update.message.reply_text(send_error_text)
        return
    
    # Confirm to manager with "View All Tasks" button
    view_all_button_text = get_text(
        language,
        'handle_task_creation.view_all_button',
        default="📋 View All Tasks"
    )
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(view_all_button_text, callback_data="view_tasks")
    ]])
    
    manager_confirmation_text = get_text(
        language,
        'handle_task_creation.manager_confirmation',
        default="✅ *Task sent to worker:*\n\"{task}\"",
        task=task_description
    )
    
    await update.message.reply_text(
        manager_confirmation_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def task_completion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle when worker clicks 'Mark Done' button"""
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    # Extract task_id from callback_data (format: "task_done_123")
    try:
        task_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        user = database.get_user(user_id)
        language = user['language'] if user else 'English'
        invalid_id_text = get_text(
            language,
            'task_completion_callback.invalid_task_id',
            default="⚠️ Invalid task ID"
        )
        await query.answer(invalid_id_text)
        return
    
    # Verify user is a worker
    user = database.get_user(user_id)
    if not user or user['role'] != 'worker':
        language = user['language'] if user else 'English'
        not_worker_text = get_text(
            language,
            'task_completion_callback.not_worker',
            default="⚠️ Only workers can complete tasks"
        )
        await query.answer(not_worker_text)
        return
    
    language = user['language']
    
    # Complete the task
    task = tasks.complete_task(task_id)
    
    if not task:
        not_found_text = get_text(
            language,
            'task_completion_callback.not_found',
            default="⚠️ Task not found or already completed"
        )
        await query.answer(not_found_text)
        return
    
    # Verify this worker is assigned to this task
    if task['worker_id'] != user_id:
        not_assigned_text = get_text(
            language,
            'task_completion_callback.not_assigned',
            default="⚠️ This task is not assigned to you"
        )
        await query.answer(not_assigned_text)
        return
    
    # Update the message to show completion
    try:
        task_completed_text = get_text(
            language,
            'task_completion_callback.task_completed',
            default="📋 *Task:*\n{task}\n\n✅ *Completed!*",
            task=task['description_translated']
        )
        await query.edit_message_text(
            text=task_completed_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error updating message: {e}")
    
    # Notify worker
    completion_confirmation = get_text(
        language,
        'task_completion_callback.completion_confirmation',
        default="✅ Task marked as completed"
    )
    await query.answer(completion_confirmation)
    
    # Notify manager
    manager_id = task['manager_id']
    manager = database.get_user(manager_id)
    if manager:
        worker_name = update.effective_user.first_name or "Worker"
        completed_time = task['completed_at'].strftime('%H:%M') if task.get('completed_at') else 'now'
        
        try:
            manager_notification = get_text(
                manager['language'],  # Use manager's language
                'task_completion_callback.manager_notification',
                default="✅ *Task completed by {worker_name}:*\n\"{task}\"\n\n🕐 Completed at: {time}",
                worker_name=worker_name,
                task=task['description'],
                time=completed_time
            )
            await context.bot.send_message(
                chat_id=manager_id,
                text=manager_notification,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Error notifying manager: {e}")

# ============================================
# MEDIA HANDLING
# ============================================

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward non-text messages (photos, videos, voice, files, etc.) as-is"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        not_registered_text = get_text(
            'English',
            'handle_media.not_registered',
            default="Please use /start to register first."
        )
        await update.message.reply_text(not_registered_text)
        return
    
    language = user['language']
    
    # Determine recipient based on role
    if user['role'] == 'manager':
        # Find worker connected to THIS bot
        bot_id = os.environ.get('BOT_ID', 'bot1')
        workers = user.get('workers', [])
        
        worker_on_this_bot = next((w for w in workers if w.get('bot_id') == bot_id), None)
        
        if not worker_on_this_bot:
            no_worker_text = get_text(
                language,
                'handle_media.manager_no_worker',
                default="⚠️ You don't have a contact connected yet.\nShare your invitation (use /mycode) with your contact."
            )
            await update.message.reply_text(no_worker_text)
            return
        
        recipient_id = worker_on_this_bot.get('worker_id')
        sender_name = update.effective_user.first_name
        # Get recipient's language for the prefix
        recipient = database.get_user(recipient_id)
        if recipient:
            prefix = get_text(
                recipient['language'],
                'handle_media.media_prefix',
                default="📎 From {sender_name}:",
                sender_name=sender_name
            )
        else:
            prefix = f"📎 From {sender_name}:"
    
    elif user['role'] == 'worker':
        recipient_id = user.get('manager')
        if not recipient_id:
            no_manager_text = get_text(
                language,
                'handle_media.worker_no_manager',
                default="⚠️ You're not connected to a contact.\nAsk your contact for their invitation link."
            )
            await update.message.reply_text(no_manager_text)
            return
        sender_name = update.effective_user.first_name
        # Get recipient's language for the prefix
        recipient = database.get_user(recipient_id)
        if recipient:
            prefix = get_text(
                recipient['language'],
                'handle_media.media_prefix',
                default="📎 From {sender_name}:",
                sender_name=sender_name
            )
        else:
            prefix = f"📎 From {sender_name}:"
    
    # Check if recipient exists
    recipient = database.get_user(recipient_id)
    if not recipient:
        contact_not_found_text = get_text(
            language,
            'handle_media.contact_not_found',
            default="⚠️ Your contact's account no longer exists.\nUse /reset to start over."
        )
        await update.message.reply_text(contact_not_found_text)
        return
    
    # Send prefix message
    await context.bot.send_message(
        chat_id=recipient_id,
        text=prefix
    )
    
    # Forward the media message as-is
    await update.message.forward(chat_id=recipient_id)

# ============================================
# MAIN APPLICATION
# ============================================

def main():
    """Start the bot"""
    # ✅ Initialize connection pool FIRST (before anything else)
    db_connection.init_connection_pool(min_conn=5, max_conn=20)
    
    config = load_config()
    app = Application.builder().token(config['telegram_token']).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_selected)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender_selected)],
            INDUSTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, industry_selected)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start),  # Allow /start to restart registration
        ],
        allow_reentry=True,  # Allow users to restart the conversation
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('menu', menu_command))
    app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern='^menu_'))
    app.add_handler(CommandHandler('tasks', tasks_command))
    app.add_handler(CommandHandler('daily', daily_command))
    app.add_handler(CommandHandler('reset', reset))
    app.add_handler(CommandHandler('subscription', subscription_command))
    app.add_handler(CommandHandler('feedback', feedback_command))
    app.add_handler(CommandHandler('mycode', mycode_command))
    app.add_handler(CommandHandler('refer', refer_command))
    app.add_handler(CommandHandler('addworker', addworker_command))
    # Add callback handlers for tasks
    app.add_handler(CallbackQueryHandler(task_completion_callback, pattern='^task_done_'))
    app.add_handler(CallbackQueryHandler(view_tasks_callback, pattern='^view_tasks$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Handle all media types (photos, videos, voice, files, stickers, etc.)
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO | 
         filters.Document.ALL | filters.LOCATION | filters.CONTACT | filters.Sticker.ALL),
        handle_media
    ))
    
    print("🤖 BridgeOS bot is running...")
    
    try:
        app.run_polling()
    finally:
        # ✅ Clean shutdown: close all database connections
        db_connection.close_all_connections()

if __name__ == '__main__':
    main()