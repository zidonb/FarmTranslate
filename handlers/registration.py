"""
Registration handler - /start, language/gender/industry selection, cancel.
Handles both manager registration (no invite code) and worker registration (with invite code).
"""
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import load_config
from utils.i18n import get_text
from utils.helpers import get_bot_slot, validate_invitation_code, generate_invitation_code, get_invite_link
from handlers import LANGUAGE, GENDER, INDUSTRY

import models.user as user_model
import models.manager as manager_model
import models.worker as worker_model
import models.connection as connection_model

logger = logging.getLogger(__name__)


# ============================================
# /start COMMAND
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with optional deep-link invite parameter."""
    user_id = update.effective_user.id
    bot_slot = get_bot_slot()
    logger.info(f"/start from user={user_id} on slot={bot_slot}")

    # --- Already registered user ---
    user = user_model.get_by_id(user_id)
    if user:
        role = manager_model.get_role(user_id)  # 'manager', 'worker', or None

        # Already-registered user clicked an invite link
        if context.args and context.args[0].startswith('invite_'):
            msg = get_text(
                user['language'],
                'start.already_registered_clicked_invite',
                default="You're already registered as {role}.\n\nUse /reset first if you want to start over.",
                role=role or 'user'
            )
            await update.message.reply_text(msg)
            return ConversationHandler.END

        # Normal welcome back
        welcome = get_text(
            user['language'],
            'start.welcome_back',
            default="Welcome back! You're registered as {role}.\n\nUse /help to see available commands.",
            role=role or 'user'
        )
        await update.message.reply_text(welcome)
        return ConversationHandler.END

    # --- New user ---
    context.user_data.clear()

    # Check for deep-link invite code
    if context.args and context.args[0].startswith('invite_'):
        code = context.args[0].replace('invite_', '')
        if not validate_invitation_code(code):
            await update.message.reply_text(
                get_text('English', 'registration.invalid_code_format',
                         default="❌ Invalid invitation code format.\n\nPlease ask your manager for a valid invitation link.")
            )
            return ConversationHandler.END
        context.user_data['invite_code'] = code
        logger.info(f"New user={user_id} arrived with invite code={code}")

    # Show language selection
    config = load_config()
    languages = config.get('languages', ['English'])
    keyboard = [languages[i:i+2] for i in range(0, len(languages), 2)]

    await update.message.reply_text(
        get_text('English', 'start.welcome_new',
                 default="Welcome to BridgeOS! 🌉\n\nSelect your language:"),
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return LANGUAGE


# ============================================
# LANGUAGE SELECTION
# ============================================

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected language."""
    selected = update.message.text
    config = load_config()
    available = config.get('languages', [])

    if selected not in available:
        keyboard = [available[i:i+2] for i in range(0, len(available), 2)]
        await update.message.reply_text(
            get_text('English', 'registration.invalid_language',
                     default="⚠️ Please select a language from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return LANGUAGE

    context.user_data['language'] = selected
    language = selected

    # Show gender selection
    male = get_text(language, 'registration.gender_options.male', default="Male")
    female = get_text(language, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(language, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")

    await update.message.reply_text(
        get_text(language, 'registration.gender_question',
                 default="What is your gender?\n(This helps with accurate translations)"),
        reply_markup=ReplyKeyboardMarkup([[male, female], [prefer_not]], one_time_keyboard=True, resize_keyboard=True)
    )
    return GENDER


# ============================================
# GENDER SELECTION
# ============================================

async def gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected gender — branch to worker completion or industry question."""
    language = context.user_data.get('language', 'English')

    # Build translated options and reverse map
    male = get_text(language, 'registration.gender_options.male', default="Male")
    female = get_text(language, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(language, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")
    reverse_map = {male: 'Male', female: 'Female', prefer_not: 'Prefer not to say'}

    if update.message.text not in reverse_map:
        await update.message.reply_text(
            get_text(language, 'registration.invalid_gender',
                     default="⚠️ Please select your gender from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup([[male, female], [prefer_not]], one_time_keyboard=True, resize_keyboard=True)
        )
        return GENDER

    context.user_data['gender'] = reverse_map[update.message.text]

    # --- Worker registration (has invite code) ---
    if 'invite_code' in context.user_data:
        return await _complete_worker_registration(update, context)

    # --- Manager registration — ask for industry ---
    config = load_config()
    industries = config.get('industries', {})
    buttons = []
    for key in industries:
        translated = get_text(language, f'industries.{key}', default=industries[key]['name'])
        buttons.append(translated)

    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    await update.message.reply_text(
        get_text(language, 'registration.industry_question',
                 default="What industry do you work in?\n\nThis helps provide accurate translations of technical terms and workplace-specific language."),
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return INDUSTRY


# ============================================
# INDUSTRY SELECTION (manager only)
# ============================================

async def industry_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User selected industry — complete manager registration."""
    user_id = update.effective_user.id
    language = context.user_data['language']
    gender = context.user_data['gender']
    industry_text = update.message.text

    config = load_config()
    industries = config.get('industries', {})

    # Reverse map: translated name → key
    reverse_map = {}
    for key in industries:
        translated = get_text(language, f'industries.{key}', default=industries[key]['name'])
        reverse_map[translated] = key

    if industry_text not in reverse_map:
        buttons = list(reverse_map.keys())
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        await update.message.reply_text(
            get_text(language, 'registration.invalid_industry',
                     default="⚠️ Please select an industry from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return INDUSTRY

    industry_key = reverse_map[industry_text]

    # Generate unique invitation code
    code = generate_invitation_code()

    # Create user + manager in database
    telegram_name = update.effective_user.first_name
    user_model.create(user_id, telegram_name=telegram_name, language=language, gender=gender)
    manager_model.create(user_id, code=code, industry=industry_key)

    logger.info(f"Manager registered: user={user_id}, code={code}, industry={industry_key}")

    # Build invitation link for current bot
    bot_info = await context.bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=invite_{code}"

    # Share button
    share_text = get_text(language, 'registration.share_invitation_text',
                          default="🌉 Join BridgeOS!\nChat with me in your language:\n{deep_link}",
                          deep_link=deep_link)
    share_btn = get_text(language, 'registration.share_invitation_button',
                         default="🚀 Send Invitation Now")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(share_btn, switch_inline_query=share_text)]
    ])

    await update.message.reply_text(
        get_text(language, 'registration.registration_complete',
                 default="✅ Registration complete!\n\n📋 Your invitation code: {code}\n🔗 Invitation link:\n{deep_link}\n\n👉 Tap the button below to share with your contact:",
                 code=code, deep_link=deep_link),
        reply_markup=keyboard
    )
    await update.message.reply_text(
        get_text(language, 'registration.ready_to_start', default="Ready to start! Use /help anytime."),
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ============================================
# WORKER REGISTRATION (internal)
# ============================================

async def _complete_worker_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete worker registration after gender selection."""
    user_id = update.effective_user.id
    language = context.user_data['language']
    gender = context.user_data['gender']
    code = context.user_data['invite_code']
    bot_slot = get_bot_slot()
    telegram_name = update.effective_user.first_name

    # Find manager by code
    manager = manager_model.get_by_code(code)
    if not manager:
        await update.message.reply_text(
            get_text(language, 'registration.invalid_code',
                     default="❌ Invalid invitation code.\n\nPlease ask your contact for a new invitation link."),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    manager_id = manager['manager_id']

    # Create user + worker records
    user_model.create(user_id, telegram_name=telegram_name, language=language, gender=gender)
    worker_model.create(user_id)

    # Attempt to create connection (database UNIQUE constraint prevents race conditions)
    try:
        connection_model.create(manager_id=manager_id, worker_id=user_id, bot_slot=bot_slot)
    except connection_model.SlotOccupiedError:
        logger.warning(f"Slot occupied: user={user_id} tried slot={bot_slot} for manager={manager_id}")
        await update.message.reply_text(
            get_text(language, 'registration.worker_already_connected',
                     default="❌ This bot slot is already occupied.\n\nAsk your manager for a different bot invitation."),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    except connection_model.WorkerAlreadyConnectedError:
        logger.warning(f"Worker already connected: user={user_id} already has active connection")
        await update.message.reply_text(
            get_text(language, 'registration.worker_already_has_manager',
                     default="❌ You're already connected to a manager.\n\nUse /reset first if you want to connect to someone else."),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    logger.info(f"Worker connected: user={user_id} → manager={manager_id} on slot={bot_slot}")

    # Confirm to worker
    await update.message.reply_text(
        get_text(language, 'registration.connection_success',
                 default="✅ Connected to your contact! You can start chatting now.\n\nUse /help to see available commands."),
        reply_markup=ReplyKeyboardRemove()
    )

    # Notify manager
    manager_user = user_model.get_by_id(manager_id)
    if manager_user:
        worker_name = telegram_name or "Worker"
        try:
            await context.bot.send_message(
                chat_id=manager_id,
                text=get_text(manager_user['language'], 'registration.manager_notification',
                              default="✅ {worker_name} connected as your worker!",
                              worker_name=worker_name)
            )
        except Exception as e:
            logger.warning(f"Could not notify manager={manager_id}: {e}")

    return ConversationHandler.END


# ============================================
# /settings — change language, gender, industry
# ============================================

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /settings — lets registered users update their language, gender, industry."""
    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)

    if not user:
        await update.message.reply_text(
            get_text('English', 'settings.not_registered',
                     default="Please use /start to register first.")
        )
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    context.user_data['settings_language'] = user['language']  # keep current as fallback

    config = load_config()
    languages = config.get('languages', ['English'])
    keyboard = [languages[i:i+2] for i in range(0, len(languages), 2)]

    await update.message.reply_text(
        get_text(user['language'], 'settings.language_question',
                 default="⚙️ Settings\n\nSelect your new language:"),
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    from handlers import SETTINGS_LANGUAGE
    return SETTINGS_LANGUAGE


async def settings_language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked a new language in settings flow."""
    selected = update.message.text
    config = load_config()
    available = config.get('languages', [])

    if selected not in available:
        keyboard = [available[i:i+2] for i in range(0, len(available), 2)]
        await update.message.reply_text(
            get_text('English', 'registration.invalid_language',
                     default="⚠️ Please select a language from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        from handlers import SETTINGS_LANGUAGE
        return SETTINGS_LANGUAGE

    context.user_data['settings_language'] = selected

    male = get_text(selected, 'registration.gender_options.male', default="Male")
    female = get_text(selected, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(selected, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")

    await update.message.reply_text(
        get_text(selected, 'registration.gender_question',
                 default="What is your gender?\n(This helps with accurate translations)"),
        reply_markup=ReplyKeyboardMarkup([[male, female], [prefer_not]], one_time_keyboard=True, resize_keyboard=True)
    )

    from handlers import SETTINGS_GENDER
    return SETTINGS_GENDER


async def settings_gender_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked a new gender in settings flow."""
    user_id = update.effective_user.id
    language = context.user_data.get('settings_language', 'English')

    male = get_text(language, 'registration.gender_options.male', default="Male")
    female = get_text(language, 'registration.gender_options.female', default="Female")
    prefer_not = get_text(language, 'registration.gender_options.prefer_not_to_say', default="Prefer not to say")
    reverse_map = {male: 'Male', female: 'Female', prefer_not: 'Prefer not to say'}

    if update.message.text not in reverse_map:
        await update.message.reply_text(
            get_text(language, 'registration.invalid_gender',
                     default="⚠️ Please select your gender from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup([[male, female], [prefer_not]], one_time_keyboard=True, resize_keyboard=True)
        )
        from handlers import SETTINGS_GENDER
        return SETTINGS_GENDER

    context.user_data['settings_gender'] = reverse_map[update.message.text]
    role = manager_model.get_role(user_id)

    if role != 'manager':
        # Worker — save and done
        user_model.update(user_id, language=language, gender=reverse_map[update.message.text])
        await update.message.reply_text(
            get_text(language, 'settings.updated',
                     default="✅ Settings updated!"),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Manager — ask for industry
    config = load_config()
    industries = config.get('industries', {})
    buttons = []
    for key in industries:
        translated = get_text(language, f'industries.{key}', default=industries[key]['name'])
        buttons.append(translated)

    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    await update.message.reply_text(
        get_text(language, 'registration.industry_question',
                 default="What industry do you work in?"),
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    from handlers import SETTINGS_INDUSTRY
    return SETTINGS_INDUSTRY


async def settings_industry_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked a new industry in settings flow — save everything."""
    user_id = update.effective_user.id
    language = context.user_data.get('settings_language', 'English')
    gender = context.user_data.get('settings_gender', 'Prefer not to say')
    industry_text = update.message.text

    config = load_config()
    industries = config.get('industries', {})
    reverse_map = {}
    for key in industries:
        translated = get_text(language, f'industries.{key}', default=industries[key]['name'])
        reverse_map[translated] = key

    if industry_text not in reverse_map:
        buttons = list(reverse_map.keys())
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        await update.message.reply_text(
            get_text(language, 'registration.invalid_industry',
                     default="⚠️ Please select an industry from the keyboard below."),
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        from handlers import SETTINGS_INDUSTRY
        return SETTINGS_INDUSTRY

    industry_key = reverse_map[industry_text]

    user_model.update(user_id, language=language, gender=gender)
    manager_model.update_industry(user_id, industry_key)

    logger.info(f"Settings updated: user={user_id}, language={language}, gender={gender}, industry={industry_key}")

    await update.message.reply_text(
        get_text(language, 'settings.updated',
                 default="✅ Settings updated!"),
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ============================================
# CANCEL
# ============================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel registration."""
    language = context.user_data.get('language', 'English')
    await update.message.reply_text(
        get_text(language, 'registration.cancelled',
                 default="Registration cancelled. Use /start to try again."),
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END
