"""
Messages handler - text message translation/forwarding and media forwarding.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import load_config
from utils.i18n import get_text
from utils.helpers import get_bot_slot, get_invite_link, get_bot_username_for_slot
from utils.translator import translate

import models.user as user_model
import models.manager as manager_model
import models.connection as connection_model
import models.message as message_model
import models.subscription as subscription_model
import models.usage as usage_model

logger = logging.getLogger(__name__)


# ============================================
# TEXT MESSAGES
# ============================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages — translate and forward."""
    user_id = update.effective_user.id
    text = update.message.text

    # Check if awaiting feedback (handled by subscriptions handler)
    if context.user_data.get('awaiting_feedback'):
        from handlers.subscriptions import _handle_feedback_response
        await _handle_feedback_response(update, context)
        return

    user = user_model.get_by_id(user_id)
    if not user:
        await update.message.reply_text(
            get_text('English', 'handle_message.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']

    # Check for task prefix
    if text.startswith('**'):
        from handlers.tasks import handle_task_creation
        await handle_task_creation(update, context)
        return

    role = manager_model.get_role(user_id)
    bot_slot = get_bot_slot()
    config = load_config()

    if role == 'manager':
        await _handle_manager_message(update, context, user, bot_slot, config)
    elif role == 'worker':
        await _handle_worker_message(update, context, user, config)
    else:
        await update.message.reply_text(
            get_text(language, 'handle_message.no_role',
                     default="⚠️ Could not determine your role. Use /reset and register again."))


async def _handle_manager_message(update, context, user, bot_slot, config):
    """Translate and forward manager's message to worker on this bot slot."""
    user_id = update.effective_user.id
    language = user['language']
    text = update.message.text

    # Check subscription / usage limits
    has_subscription = subscription_model.is_active(user_id)
    if not has_subscription:
        if usage_model.is_blocked(user_id):
            await _send_limit_reached(update, user_id, language, config)
            return

    # Find connection on this bot
    conn = connection_model.get_by_manager_and_slot(user_id, bot_slot)
    if not conn:
        manager = manager_model.get_by_id(user_id)
        code = manager['code'] if manager else ''
        bot_username = get_bot_username_for_slot(bot_slot)
        invite_link = get_invite_link(bot_username, code)
        await update.message.reply_text(
            get_text(language, 'handle_message.manager.no_worker',
                     default="⚠️ You don't have a worker connected to this bot yet.\n\n"
                             "Share your invitation to connect a worker:\n\n"
                             "📋 Code: {code}\n🔗 {invite_link}",
                     code=code, invite_link=invite_link))
        return

    worker_id = conn['worker_id']
    worker = user_model.get_by_id(worker_id)
    if not worker:
        await update.message.reply_text(
            get_text(language, 'handle_message.manager.worker_not_found',
                     default="⚠️ Your contact's account no longer exists.\nUse /reset to start over."))
        return

    # Get translation context
    manager_data = manager_model.get_by_id(user_id)
    industry_key = manager_data.get('industry', 'other') if manager_data else 'other'
    context_size = config.get('translation_context_size', 3)
    history = message_model.get_translation_context(conn['connection_id'], limit=context_size)

    # Translate
    translation_failed = False
    try:
        translated = translate(
            text=text,
            from_lang=language,
            to_lang=worker['language'],
            target_gender=worker.get('gender'),
            conversation_history=history,
            industry=industry_key
        )
    except Exception as e:
        logger.error(f"Translation failed for manager={user_id}: {e}")
        translated = text
        translation_failed = True

    # Save message
    message_model.save(
        connection_id=conn['connection_id'],
        sender_id=user_id,
        original_text=text,
        translated_text=translated
    )

    # Forward to worker
    manager_name = update.effective_user.first_name or "Manager"
    forward_text = get_text(worker['language'], 'handle_message.manager.message_prefix',
                            default="🗣️ From {name}: {translated}",
                            name=manager_name, translated=translated)
    if translation_failed:
        warning = get_text(worker['language'], 'handle_message.translation_unavailable',
                           default="⚠️ Translation temporarily unavailable. Original message:")
        forward_text = f"{warning}\n\n🗣️ {manager_name}: {text}"
    await context.bot.send_message(chat_id=worker_id, text=forward_text)

    # Notify sender
    if translation_failed:
        await update.message.reply_text(
            get_text(language, 'handle_message.translation_error',
                     default="⚠️ Translation temporarily unavailable. Your message was forwarded as-is."))

    # Increment usage (only if no subscription)
    if not has_subscription:
        allowed = usage_model.increment(user_id)
        if not allowed:
            await _send_last_message_warning(update, user_id, language, config)

    logger.info(f"Message: manager={user_id} → worker={worker_id} on slot={bot_slot}")


async def _handle_worker_message(update, context, user, config):
    """Translate and forward worker's message to manager."""
    user_id = update.effective_user.id
    language = user['language']
    text = update.message.text

    conn = connection_model.get_active_for_worker(user_id)
    if not conn:
        await update.message.reply_text(
            get_text(language, 'handle_message.worker.no_manager',
                     default="⚠️ You're not connected to a contact.\nAsk your contact for their invitation link."))
        return

    manager_id = conn['manager_id']
    manager_user = user_model.get_by_id(manager_id)
    if not manager_user:
        await update.message.reply_text(
            get_text(language, 'handle_message.worker.manager_not_found',
                     default="⚠️ Your contact's account no longer exists.\nUse /reset and wait for a new invitation."))
        return

    # Get translation context
    manager_data = manager_model.get_by_id(manager_id)
    industry_key = manager_data.get('industry', 'other') if manager_data else 'other'
    context_size = config.get('translation_context_size', 3)
    history = message_model.get_translation_context(conn['connection_id'], limit=context_size)

    # Translate
    translation_failed = False
    try:
        translated = translate(
            text=text,
            from_lang=language,
            to_lang=manager_user['language'],
            target_gender=manager_user.get('gender'),
            conversation_history=history,
            industry=industry_key
        )
    except Exception as e:
        logger.error(f"Translation failed for worker={user_id}: {e}")
        translated = text
        translation_failed = True

    # Save message
    message_model.save(
        connection_id=conn['connection_id'],
        sender_id=user_id,
        original_text=text,
        translated_text=translated
    )

    # Forward to manager
    sender_name = update.effective_user.first_name or "Worker"
    forward_text = get_text(manager_user['language'], 'handle_message.worker.message_prefix',
                            default="🗣️ From {name}: {translated}",
                            name=sender_name, translated=translated)
    if translation_failed:
        warning = get_text(manager_user['language'], 'handle_message.translation_unavailable',
                           default="⚠️ Translation temporarily unavailable. Original message:")
        forward_text = f"{warning}\n\n🗣️ {sender_name}: {text}"
    await context.bot.send_message(chat_id=manager_id, text=forward_text)

    # Notify sender
    if translation_failed:
        await update.message.reply_text(
            get_text(language, 'handle_message.translation_error',
                     default="⚠️ Translation temporarily unavailable. Your message was forwarded as-is."))

    logger.info(f"Message: worker={user_id} → manager={manager_id}")


# ============================================
# MEDIA FORWARDING
# ============================================

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward non-text messages (photos, videos, voice, files, etc.) as-is."""
    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)

    if not user:
        await update.message.reply_text(
            get_text('English', 'handle_media.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)
    bot_slot = get_bot_slot()

    # Determine recipient
    if role == 'manager':
        conn = connection_model.get_by_manager_and_slot(user_id, bot_slot)
        if not conn:
            await update.message.reply_text(
                get_text(language, 'handle_media.manager_no_worker',
                         default="⚠️ You don't have a worker connected to this bot yet."))
            return
        recipient_id = conn['worker_id']

    elif role == 'worker':
        conn = connection_model.get_active_for_worker(user_id)
        if not conn:
            await update.message.reply_text(
                get_text(language, 'handle_media.worker_no_manager',
                         default="⚠️ You're not connected to a contact.\nAsk your contact for their invitation link."))
            return
        recipient_id = conn['manager_id']

    else:
        await update.message.reply_text(
            get_text(language, 'handle_media.invalid_role',
                     default="⚠️ Your account has an invalid role.\nPlease use /reset and register again."))
        return

    # Check recipient exists
    recipient = user_model.get_by_id(recipient_id)
    if not recipient:
        await update.message.reply_text(
            get_text(language, 'handle_media.contact_not_found',
                     default="⚠️ Your contact's account no longer exists.\nUse /reset to start over."))
        return

    # Send prefix + forward media
    sender_name = update.effective_user.first_name or "User"
    prefix = get_text(recipient['language'], 'handle_media.media_prefix',
                      default="📎 From {sender_name}:",
                      sender_name=sender_name)
    await context.bot.send_message(chat_id=recipient_id, text=prefix)
    await update.message.forward(chat_id=recipient_id)

    logger.info(f"Media forwarded: {user_id} → {recipient_id}")


# ============================================
# USAGE LIMIT HELPERS
# ============================================

async def _send_limit_reached(update, user_id, language, config):
    """Send message limit reached notification with upgrade button."""
    monthly_price = config.get('lemonsqueezy', {}).get('monthly_price', 9.00)
    free_limit = config.get('free_message_limit', 50)

    checkout_url = subscription_model.create_checkout_url(user_id)
    button_text = get_text(language, 'handle_message.limit_reached.button',
                           default="💳 Upgrade to Business License (${price}/month)",
                           price=f"{monthly_price:.0f}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, url=checkout_url)]
    ])

    msg = (get_text(language, 'handle_message.limit_reached.title',
                    default="⚠️ *Free Plan Limit Reached*\n\n") +
           get_text(language, 'handle_message.limit_reached.message',
                    default="Your business has used its allocation of {free_limit} translated messages.\n"
                            "To continue, please upgrade your account.\n\n",
                    free_limit=free_limit) +
           get_text(language, 'handle_message.limit_reached.cta',
                    default="Tap below to upgrade:"))

    await update.message.reply_text(msg, reply_markup=keyboard, parse_mode='Markdown')


async def _send_last_message_warning(update, user_id, language, config):
    """Send warning that user just used their last free message."""
    monthly_price = config.get('lemonsqueezy', {}).get('monthly_price', 9.00)
    free_limit = config.get('free_message_limit', 50)

    checkout_url = subscription_model.create_checkout_url(user_id)
    button_text = get_text(language, 'handle_message.manager.last_message_button',
                           default="🏢 Upgrade to Business License (${price}/month)",
                           price=f"{monthly_price:.0f}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, url=checkout_url)]
    ])

    await update.message.reply_text(
        get_text(language, 'handle_message.manager.last_message',
                 default="⚠️ *That was your last free message!*\n\nYou've used all {free_limit} free messages.\n\n"
                         "💳 Subscribe for unlimited messages (${price}/month):",
                 free_limit=free_limit, price=f"{monthly_price:.0f}"),
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
