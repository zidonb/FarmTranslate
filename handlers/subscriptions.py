"""
Subscriptions handler - /subscription, /refer, /feedback.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import load_config
import random
from utils.i18n import get_text
from utils.helpers import BOT_USERNAMES
import models.user as user_model
import models.manager as manager_model
import models.subscription as subscription_model
import models.usage as usage_model
import models.feedback as feedback_model

logger = logging.getLogger(__name__)


# ============================================
# HELPERS
# ============================================

def _get_user_and_send(update: Update):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        send_message = update.callback_query.message.reply_text
    else:
        user_id = update.effective_user.id
        send_message = update.message.reply_text
    return user_id, send_message


# ============================================
# /subscription
# ============================================

async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription status and management."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'subscription.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role != 'manager':
        await send_message(
            get_text(language, 'subscription.worker_unlimited',
                     default="Workers have unlimited messages! 🎉\n\nOnly managers need subscriptions."),
            parse_mode='Markdown')
        return

    config = load_config()
    monthly_price = config.get('lemonsqueezy', {}).get('monthly_price', 9.00)
    free_limit = config.get('free_message_limit', 50)

    sub = subscription_model.get_by_manager(user_id)

    if not sub or sub.get('status') in ('expired', 'free', None):
        # No subscription — show subscribe option
        checkout_url = subscription_model.create_checkout_url(user_id)
        usage = usage_model.get(user_id)
        messages_sent = usage.get('messages_sent', 0) if usage else 0

        button = get_text(language, 'subscription.no_subscription.button',
                          default="🏢 Upgrade to Business License (${price}/month)",
                          price=f"{monthly_price:.0f}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(button, url=checkout_url)]
        ])

        msg = (get_text(language, 'subscription.no_subscription.title',
                        default="📋 *Subscription Status*\n\n") +
               get_text(language, 'subscription.no_subscription.status',
                        default="Status: ❌ No Active Subscription\n") +
               get_text(language, 'subscription.no_subscription.usage',
                        default="Messages Used: {messages_sent} / {free_limit} (Free Tier)\n\n",
                        messages_sent=messages_sent, free_limit=free_limit) +
               get_text(language, 'subscription.no_subscription.benefits_header',
                        default="💳 *Subscribe to BridgeOS:*\n") +
               get_text(language, 'subscription.no_subscription.benefits',
                        default="• Unlimited messages\n• ${price}/month\n• Cancel anytime",
                        price=f"{monthly_price:.0f}"))

        await send_message(msg, reply_markup=keyboard, parse_mode='Markdown')

    else:
        # Has subscription
        status = sub.get('status', 'unknown')
        renews_at = str(sub.get('renews_at', 'N/A'))[:10] if sub.get('renews_at') else 'N/A'
        ends_at = sub.get('ends_at')
        portal_url = sub.get('customer_portal_url')

        emoji = {'active': '✅', 'cancelled': '⚠️', 'paused': '⏸️', 'expired': '❌'}.get(status, '❓')

        msg = (get_text(language, 'subscription.active_subscription.title',
                        default="📋 *Your Subscription*\n\n") +
               get_text(language, 'subscription.active_subscription.status',
                        default="{emoji} Status: {status}\n",
                        emoji=emoji, status=status.title()) +
               get_text(language, 'subscription.active_subscription.plan',
                        default="💳 Plan: Unlimited Messages\n") +
               get_text(language, 'subscription.active_subscription.price',
                        default="💵 Price: ${price}/month\n",
                        price=f"{monthly_price:.0f}"))

        if status == 'active':
            msg += get_text(language, 'subscription.active_subscription.renews',
                            default="📅 Renews: {date}\n", date=renews_at)
        elif status == 'cancelled' and ends_at:
            msg += get_text(language, 'subscription.active_subscription.access_until',
                            default="📅 Access Until: {date}\n", date=str(ends_at)[:10])

        msg += get_text(language, 'subscription.active_subscription.footer',
                        default="\n_Manage or cancel anytime._")

        if portal_url:
            manage_btn = get_text(language, 'subscription.active_subscription.manage_button',
                                  default="⚙️ Manage Business License")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(manage_btn, url=portal_url)]
            ])
            await send_message(msg, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await send_message(msg, parse_mode='Markdown')


# ============================================
# /refer
# ============================================

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let users share BridgeOS with other managers."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)
    language = user['language'] if user else 'English'

    config = load_config()
    language_count = len(config.get('languages', []))

    random_bot = random.choice(list(BOT_USERNAMES.values()))
    bot_link = f"https://t.me/{random_bot}"

    share_text = get_text(language, 'refer.share_text',
                          default="🌉 Check out BridgeOS!\n\nI use it to communicate with my team in real-time - "
                                  "we speak different languages but chat naturally!\n\n"
                                  "🌐 {language_count} languages supported\n"
                                  "✅ Instant translation\n🏭 Industry-specific terms\n"
                                  "💬 Simple & effective\n\nTry it free: {bot_link}",
                          language_count=language_count, bot_link=bot_link)
    button = get_text(language, 'refer.button', default="📤 Recommend BridgeOS")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button, switch_inline_query=share_text)]
    ])

    await send_message(
        get_text(language, 'refer.message',
                 default="🌉 Love BridgeOS?\n\nHelp other managers break language barriers!\n\n"
                         "Recommend BridgeOS to colleagues, friends, or anyone who manages teams "
                         "speaking different languages.\n\n👉 Tap the button to share:"),
        reply_markup=keyboard
    )


# ============================================
# /feedback
# ============================================

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to send feedback."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)
    language = user['language'] if user else 'English'

    context.user_data['awaiting_feedback'] = True

    await send_message(
        get_text(language, 'feedback.prompt',
                 default="💡 *Send Your Feedback*\n\nType your message below and I'll forward it to the BridgeOS team.\n\n"
                         "Share suggestions, report bugs, or tell us what you think!"),
        parse_mode='Markdown'
    )


async def _handle_feedback_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the feedback message (called from messages handler)."""
    context.user_data['awaiting_feedback'] = False

    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)
    language = user['language'] if user else 'English'

    config = load_config()
    admin_id = config.get('admin_telegram_id')

    if not admin_id:
        await update.message.reply_text(
            get_text(language, 'feedback_handling.admin_error',
                     default="⚠️ Error: Admin not configured. Please contact support."))
        return

    user_name = update.effective_user.first_name or "Unknown"
    username = update.effective_user.username
    text = update.message.text

    # Format and send to admin
    feedback_msg = f"💬 *Feedback from {user_name}*\n"
    if username:
        feedback_msg += f"@{username} "
    feedback_msg += f"(ID: {user_id})\n\n{text}"

    try:
        await context.bot.send_message(chat_id=admin_id, text=feedback_msg)
        feedback_model.save(user_id=user_id, telegram_name=user_name, username=username, message=text)

        await update.message.reply_text(
            get_text(language, 'feedback_handling.success',
                     default="✅ *Feedback Sent!*\n\nThank you for sharing your thoughts with us. "
                             "We read every message and truly appreciate your input!"),
            parse_mode='Markdown')
        logger.info(f"Feedback received from user={user_id}")

    except Exception as e:
        logger.error(f"Error sending feedback from user={user_id}: {e}")
        await update.message.reply_text(
            get_text(language, 'feedback_handling.error',
                     default="⚠️ Sorry, there was an error sending your feedback. Please try again later."))
