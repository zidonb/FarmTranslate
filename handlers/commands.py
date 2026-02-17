"""
Commands handler - /help, /menu, /resetall, menu callback routing.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.i18n import get_text
import models.user as user_model
import models.manager as manager_model
import models.worker as worker_model
import models.connection as connection_model
import models.subscription as subscription_model

logger = logging.getLogger(__name__)


# ============================================
# HELPERS
# ============================================

def _get_user_and_send(update: Update):
    """Extract user_id and send_message from either command or callback."""
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        send_message = update.callback_query.message.reply_text
        first_name = update.callback_query.from_user.first_name
    else:
        user_id = update.effective_user.id
        send_message = update.message.reply_text
        first_name = update.effective_user.first_name
    return user_id, send_message, first_name


# ============================================
# /help
# ============================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available commands based on role."""
    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)

    if not user:
        await update.message.reply_text(
            get_text('English', 'help.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role == 'manager':
        text = get_text(language, 'help.manager_commands',
                        default="📋 *Available Commands:*\n\n"
                                "/help - Show this help message\n"
                                "/tasks - View your task list\n"
                                "/daily - Get daily action items\n"
                                "/addworker - Add a new worker\n"
                                "/workers - View your workers\n"
                                "/subscription - View subscription status\n"
                                "/refer - Recommend to other managers\n"
                                "/feedback - Send feedback to BridgeOS team\n"
                                "/resetall - Delete account and start over\n\n"
                                "💬 *How to use:*\n"
                                "Just type your message and it will be automatically translated and sent to your contact!")
    else:
        text = get_text(language, 'help.worker_commands',
                        default="📋 *Available Commands:*\n\n"
                                "/help - Show this help message\n"
                                "/tasks - View your task list\n"
                                "/refer - Recommend to other managers\n"
                                "/feedback - Send feedback to BridgeOS team\n"
                                "/resetall - Delete account\n\n"
                                "💬 *How to use:*\n"
                                "Just type your message and it will be automatically translated and sent to your contact!")

    await update.message.reply_text(text, parse_mode='Markdown')


# ============================================
# /menu
# ============================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show role-aware menu with inline buttons."""
    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)

    if not user:
        await update.message.reply_text(
            get_text('English', 'menu.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role == 'manager':
        buttons = [
            [InlineKeyboardButton(get_text(language, 'menu.tasks', default='📋 My Tasks'), callback_data='menu_tasks')],
            [InlineKeyboardButton(get_text(language, 'menu.daily', default='📊 Daily Action Items'), callback_data='menu_daily')],
            [InlineKeyboardButton(get_text(language, 'menu.workers', default='👥 My Workers'), callback_data='menu_workers')],
            [InlineKeyboardButton(get_text(language, 'menu.addworker', default='➕ Add Worker'), callback_data='menu_addworker')],
            [InlineKeyboardButton(get_text(language, 'menu.subscription', default='💳 Subscription'), callback_data='menu_subscription')],
            [InlineKeyboardButton(get_text(language, 'menu.refer', default='📤 Refer BridgeOS'), callback_data='menu_refer')],
            [InlineKeyboardButton(get_text(language, 'menu.feedback', default='💬 Send Feedback'), callback_data='menu_feedback')],
            [InlineKeyboardButton(get_text(language, 'menu.resetall', default='🗑️ Reset All'), callback_data='menu_resetall')],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(get_text(language, 'menu.tasks', default='📋 My Tasks'), callback_data='menu_tasks')],
            [InlineKeyboardButton(get_text(language, 'menu.refer', default='📤 Refer BridgeOS'), callback_data='menu_refer')],
            [InlineKeyboardButton(get_text(language, 'menu.feedback', default='💬 Send Feedback'), callback_data='menu_feedback')],
            [InlineKeyboardButton(get_text(language, 'menu.resetall', default='🗑️ Reset All'), callback_data='menu_resetall')],
        ]

    await update.message.reply_text(
        get_text(language, 'menu.title', default='📋 BridgeOS Menu\n\nSelect an option:'),
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route menu button presses to the appropriate handler."""
    query = update.callback_query
    await query.answer()

    # Import handlers lazily to avoid circular imports
    from handlers.connections import addworker_command, workers_command
    from handlers.tasks import tasks_command, daily_command
    from handlers.subscriptions import subscription_command, refer_command, feedback_command

    routing = {
        'menu_tasks':        tasks_command,
        'menu_daily':        daily_command,
        'menu_addworker':    addworker_command,
        'menu_workers':      workers_command,
        'menu_subscription': subscription_command,
        'menu_refer':        refer_command,
        'menu_feedback':     feedback_command,
        'menu_resetall':     resetall_command,
    }

    handler = routing.get(query.data)
    if handler:
        await handler(update, context)


# ============================================
# /resetall
# ============================================

async def resetall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset entire user account — soft-delete all data, disconnect all connections."""
    user_id, send_message, first_name = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'resetall.no_account',
                     default="You don't have an account to reset."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role == 'manager':
        # Check for active subscription — block reset if still active
        sub = subscription_model.get_by_manager(user_id)
        if sub and sub['status'] in ('active', 'paused'):
            portal_url = sub.get('customer_portal_url', '')
            if portal_url:
                await send_message(
                    get_text(language, 'resetall.active_subscription',
                             default="⚠️ You have an active subscription.\n\n"
                                     "Please cancel it first before resetting your account:\n{portal_url}\n\n"
                                     "After cancelling, use /resetall again.",
                             portal_url=portal_url))
            else:
                await send_message(
                    get_text(language, 'resetall.active_subscription_no_portal',
                             default="⚠️ You have an active subscription.\n\n"
                                     "Please cancel it first before resetting your account.\n"
                                     "Use /subscription to manage your billing."))
            return

        # Get all active connections before disconnecting
        connections = connection_model.get_active_for_manager(user_id)

        # Disconnect all connections
        for conn in connections:
            connection_model.disconnect(conn['connection_id'])

            # Notify each worker (best effort)
            worker_user = user_model.get_by_id(conn['worker_id'])
            if worker_user:
                try:
                    await context.bot.send_message(
                        chat_id=conn['worker_id'],
                        text=get_text(worker_user['language'], 'resetall.worker_notification',
                                      default="⚠️ Your contact has reset their account.\n\n"
                                              "You'll need a new invitation to reconnect."))
                except Exception as e:
                    logger.warning(f"Could not notify worker={conn['worker_id']}: {e}")

        # Soft-delete manager record
        manager_model.soft_delete(user_id)
        logger.info(f"Manager resetall: user={user_id}, disconnected {len(connections)} workers")

    elif role == 'worker':
        # Get active connection
        conn = connection_model.get_active_for_worker(user_id)
        if conn:
            connection_model.disconnect(conn['connection_id'])

            # Notify manager (best effort)
            manager_user = user_model.get_by_id(conn['manager_id'])
            if manager_user:
                worker_name = first_name or "Worker"
                try:
                    await context.bot.send_message(
                        chat_id=conn['manager_id'],
                        text=get_text(manager_user['language'], 'resetall.manager_notification',
                                      default="ℹ️ {worker_name} has reset their account and is no longer connected.",
                                      worker_name=worker_name))
                except Exception as e:
                    logger.warning(f"Could not notify manager={conn['manager_id']}: {e}")

        # Soft-delete worker record
        worker_model.soft_delete(user_id)
        logger.info(f"Worker resetall: user={user_id}")

    # Delete user record (hard delete — cascades via FK)
    user_model.delete(user_id)

    await send_message(
        get_text(language, 'resetall.success',
                 default="✅ Your account has been reset!\n\n"
                         "All your data and connections have been deleted.\n"
                         "Use /start to register again."))