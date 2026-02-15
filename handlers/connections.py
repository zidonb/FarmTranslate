"""
Connections handler - /addworker, /workers.
Manages the multi-bot connection flow between managers and workers.
"""
import os
import logging
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import load_config
from utils.i18n import get_text
from utils.helpers import get_bot_slot, get_bot_username_for_slot, get_invite_link

import models.user as user_model
import models.manager as manager_model
import models.connection as connection_model

logger = logging.getLogger(__name__)


# ============================================
# HELPERS
# ============================================

def _get_user_and_send(update: Update):
    """Extract user_id and send_message from either command or callback."""
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        send_message = update.callback_query.message.reply_text
    else:
        user_id = update.effective_user.id
        send_message = update.message.reply_text
    return user_id, send_message


# ============================================
# /addworker
# ============================================

async def addworker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Find next free bot slot and generate invitation link for manager."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'addworker.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    manager = manager_model.get_by_id(user_id)

    if not manager:
        await send_message(
            get_text(language, 'addworker.not_manager',
                     default="⚠️ Only managers can add workers.\n\nWorkers are added by their managers."))
        return

    code = manager['code']

    # Get occupied slots
    active_connections = connection_model.get_active_for_manager(user_id)
    occupied_slots = {conn['bot_slot'] for conn in active_connections}

    # Find available slots
    all_slots = {1, 2, 3, 4, 5}
    available = sorted(all_slots - occupied_slots)

    if not available:
        await send_message(
            get_text(language, 'addworker.all_bots_used',
                     default="⚠️ All 5 worker slots are in use.\n\nTo add another worker, disconnect an existing one first."),
            parse_mode='Markdown')
        return

    # Pick next available slot
    next_slot = available[0]
    next_bot_username = get_bot_username_for_slot(next_slot)
    invite_link = get_invite_link(next_bot_username, code)
    bot_chat_link = f"https://t.me/{next_bot_username}"

    logger.info(f"Addworker: manager={user_id} → slot={next_slot}, link={invite_link}")

    # Try to send proactive message from the next bot
    token_key = f"TELEGRAM_TOKEN_BOT{next_slot}"
    next_bot_token = os.environ.get(token_key)

    if next_bot_token:
        try:
            next_bot = Bot(token=next_bot_token)

            share_text = get_text(language, 'addworker.share_invitation_text',
                                  default="🌉 Join BridgeOS!\nChat with me in your language:\n{invite_link}",
                                  invite_link=invite_link)
            share_btn = get_text(language, 'addworker.share_button',
                                 default="🚀 Share Invitation")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(share_btn, switch_inline_query=share_text)]
            ])

            await next_bot.send_message(
                chat_id=user_id,
                text=get_text(language, 'addworker.bot_greeting',
                              default="👋 *Ready to add a worker!*\n\n📋 Share this invitation with your worker:\n\n👉 Tap the button below to share:"),
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send proactive message from bot slot {next_slot}: {e}")

    # Confirm in current bot
    await send_message(
        get_text(language, 'addworker.success',
                 default="✅ *Worker Slot Assigned on Bot {slot}*\n\n"
                         "📱 Open this bot to add your worker:\n{bot_link}\n\n"
                         "💡 The invitation is waiting for you there!",
                 bot_name=f"Bot {next_slot}", slot=next_slot, bot_link=bot_chat_link),
        parse_mode='Markdown'
    )


# ============================================
# /workers
# ============================================

async def workers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show overview of all worker slots across all bots."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'workers.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    manager = manager_model.get_by_id(user_id)

    if not manager:
        await send_message(
            get_text(language, 'workers.not_manager',
                     default="Only managers can view workers.\n\nWorkers are managed by their managers."))
        return

    # Get active connections
    connections = connection_model.get_active_for_manager(user_id)
    slot_map = {conn['bot_slot']: conn for conn in connections}

    response = get_text(language, 'workers.title', default="👥 *Your Workers*\n\n")

    for slot in range(1, 6):
        bot_name = f"Bot {slot}"
        conn = slot_map.get(slot)

        if conn:
            # Try to get worker's Telegram name
            try:
                worker_chat = await context.bot.get_chat(conn['worker_id'])
                worker_name = worker_chat.first_name or f"Worker {conn['worker_id']}"
            except Exception:
                worker_name = f"Worker {conn['worker_id']}"

            response += get_text(language, 'workers.bot_connected',
                                 default="{bot_name}: {worker_name} ✅\n",
                                 bot_name=bot_name, worker_name=worker_name)
        else:
            response += get_text(language, 'workers.bot_available',
                                 default="{bot_name}: Available\n",
                                 bot_name=bot_name)

    response += get_text(language, 'workers.footer',
                         default="\n💡 To add a worker: /addworker\n💡 To message a worker: Open that bot's chat")

    await send_message(response, parse_mode='Markdown')
