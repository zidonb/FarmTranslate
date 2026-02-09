"""
Tasks handler - /tasks, /daily, task creation (** prefix), task completion callback.
"""
import logging
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import load_config
from utils.i18n import get_text
from utils.helpers import get_bot_slot
from utils.translator import translate, generate_daily_actionitems

import models.user as user_model
import models.manager as manager_model
import models.connection as connection_model
import models.task as task_model
import models.message as message_model

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
# /tasks
# ============================================

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task list for manager or worker."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'tasks.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role == 'manager':
        await _show_manager_tasks(user_id, language, send_message, context)
    elif role == 'worker':
        await _show_worker_tasks(user_id, language, send_message)
    else:
        await send_message(
            get_text(language, 'tasks.no_role',
                     default="⚠️ Could not determine your role. Use /reset and register again."))


async def _show_manager_tasks(manager_id, language, send_message, context):
    """Format and display tasks for a manager, grouped by worker."""
    pending = task_model.get_manager_tasks(manager_id, status='pending')
    completed = task_model.get_manager_tasks(manager_id, status='completed', limit_hours=24)

    if not pending and not completed:
        await send_message(
            get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n") +
            get_text(language, 'tasks.manager.no_tasks',
                     default="No tasks yet.\n\nCreate a task by sending a message starting with **\nExample: ** Check cow 115 for heat"),
            parse_mode='Markdown')
        return

    response = get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n")

    if pending:
        response += get_text(language, 'tasks.manager.pending_header',
                             default="⏳ *PENDING ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(pending))
        # Group by worker
        by_worker = defaultdict(list)
        for t in pending:
            by_worker[t.get('worker_id')].append(t)

        for worker_id, worker_tasks in by_worker.items():
            worker_name = await _get_worker_name(context, worker_id)
            response += f"\n👤 *{worker_name}:*\n"
            for t in worker_tasks:
                time_str = t['created_at'].strftime('%H:%M') if t.get('created_at') else 'Unknown'
                response += get_text(language, 'tasks.manager.task_item',
                                     default="• {description}\n  _Created: Today at {time}_\n\n",
                                     description=t['description'], time=time_str)

    if completed:
        response += get_text(language, 'tasks.manager.completed_header',
                             default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(completed))
        by_worker = defaultdict(list)
        for t in completed:
            by_worker[t.get('worker_id')].append(t)

        for worker_id, worker_tasks in by_worker.items():
            worker_name = await _get_worker_name(context, worker_id)
            response += f"\n👤 *{worker_name}:*\n"
            for t in worker_tasks:
                time_str = t['completed_at'].strftime('%H:%M') if t.get('completed_at') else 'Unknown'
                response += get_text(language, 'tasks.manager.completed_item',
                                     default="• {description}\n  _Completed at {time}_\n\n",
                                     description=t['description'], time=time_str)

    await send_message(response, parse_mode='Markdown')


async def _show_worker_tasks(worker_id, language, send_message):
    """Format and display tasks for a worker."""
    pending = task_model.get_worker_tasks(worker_id, status='pending')
    completed = task_model.get_worker_tasks(worker_id, status='completed', limit_hours=24)

    if not pending and not completed:
        await send_message(
            get_text(language, 'tasks.worker.title', default="📋 *Your Tasks*\n\n") +
            get_text(language, 'tasks.worker.no_tasks',
                     default="No tasks assigned yet.\n\nYour manager will send you tasks when needed."),
            parse_mode='Markdown')
        return

    response = get_text(language, 'tasks.worker.title', default="📋 *Your Tasks*\n\n")

    if pending:
        response += get_text(language, 'tasks.worker.todo_header',
                             default="⏳ *TO DO ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(pending))
        for t in pending:
            response += get_text(language, 'tasks.worker.task_item',
                                 default="• {description}\n\n",
                                 description=t['description'])
        response += get_text(language, 'tasks.worker.instruction',
                             default="_Tap the ✅ Mark Done button on each task message to complete it._\n\n")

    if completed:
        response += get_text(language, 'tasks.worker.completed_header',
                             default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(completed))
        for t in completed:
            response += get_text(language, 'tasks.worker.completed_item',
                                 default="• {description} ✓\n",
                                 description=t['description'])

    await send_message(response, parse_mode='Markdown')


async def _get_worker_name(context, worker_id):
    """Get worker's Telegram first name, with fallback."""
    try:
        chat = await context.bot.get_chat(worker_id)
        return chat.first_name or f"Worker {worker_id}"
    except Exception:
        return f"Worker {worker_id}"


# ============================================
# /daily
# ============================================

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI-powered action items from last 24h conversations."""
    user_id, send_message = _get_user_and_send(update)
    user = user_model.get_by_id(user_id)

    if not user:
        await send_message(
            get_text('English', 'daily.not_registered',
                     default="Please use /start to register first."))
        return

    language = user['language']
    role = manager_model.get_role(user_id)

    if role != 'manager':
        await send_message(
            get_text(language, 'daily.not_manager',
                     default="Only managers can generate summaries.\n\nThis feature helps managers track action items and tasks."))
        return

    manager = manager_model.get_by_id(user_id)
    connections = connection_model.get_active_for_manager(user_id)

    if not connections:
        await send_message(
            get_text(language, 'daily.no_worker',
                     default="You don't have a worker connected yet.\n\nConnect with a worker first to see conversation summaries."))
        return

    generating_msg = await send_message(
        get_text(language, 'daily.generating',
                 default="⏳ Generating Daily Action Items (Last 24 Hours)...\n\nAnalyzing last 24 hours of conversation."))

    try:
        all_messages = []
        for conn in connections:
            worker_name = await _get_worker_name(context, conn['worker_id'])
            messages = message_model.get_recent(conn['connection_id'], hours=24)
            for msg in messages:
                msg['worker_name'] = worker_name
            all_messages.extend(messages)

        industry_key = manager.get('industry', 'other') if manager else 'other'
        action_items = generate_daily_actionitems(all_messages, industry=industry_key, manager_language=language)

        response = get_text(language, 'daily.result_header',
                            default="📋 *Daily Action Items (Last 24 Hours)*\n\n{action_items}",
                            action_items=action_items)
        if all_messages:
            response += get_text(language, 'daily.message_count',
                                 default="\n\n_Total messages: {count}_",
                                 count=len(all_messages))

        await generating_msg.delete()
        await send_message(response, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error generating daily action items for manager={user_id}: {e}")
        await generating_msg.delete()
        await send_message(
            get_text(language, 'daily.error',
                     default="❌ Error generating daily action items: {error}\n\nPlease try again later.",
                     error=str(e)))


# ============================================
# TASK CREATION (** prefix in message)
# ============================================

async def handle_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task creation when manager sends ** prefix."""
    user_id = update.effective_user.id
    user = user_model.get_by_id(user_id)
    language = user['language']
    text = update.message.text
    bot_slot = get_bot_slot()

    role = manager_model.get_role(user_id)
    if role != 'manager':
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.not_manager',
                     default="⚠️ Only managers can create tasks.\nTo send a regular message, don't use **"))
        return

    manager = manager_model.get_by_id(user_id)
    conn = connection_model.get_by_manager_and_slot(user_id, bot_slot)

    if not conn:
        code = manager['code'] if manager else ''
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.no_worker',
                     default="⚠️ You don't have a worker connected to this bot yet.\n\nUse /addworker to connect a worker."))
        return

    worker_id = conn['worker_id']
    worker = user_model.get_by_id(worker_id)
    if not worker:
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.worker_not_found',
                     default="⚠️ Your worker's account no longer exists.\nUse /addworker to add a new worker."))
        return

    # Extract task description
    task_description = text[2:].strip()
    if not task_description:
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.empty_description',
                     default="⚠️ Please provide a task description after **\n\nExample: ** Check cow 115 for heat"))
        return

    # Translate task
    try:
        translated = translate(
            text=task_description,
            from_lang=user['language'],
            to_lang=worker['language'],
            target_gender=worker.get('gender'),
            industry=manager.get('industry') if manager else None
        )
    except Exception as e:
        logger.error(f"Error translating task: {e}")
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.translation_error',
                     default="⚠️ Error translating task. Please try again."))
        return

    # Save task
    try:
        task_id = task_model.create(
            connection_id=conn['connection_id'],
            description=task_description,
            description_translated=translated
        )
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.creation_error',
                     default="⚠️ Error creating task. Please try again."))
        return

    # Send to worker
    mark_done_btn = get_text(worker['language'], 'handle_task_creation.mark_done_button', default="✅ Mark Done")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(mark_done_btn, callback_data=f"task_done_{task_id}")]
    ])
    manager_name = update.effective_user.first_name or "Manager"

    try:
        await context.bot.send_message(
            chat_id=worker_id,
            text=get_text(worker['language'], 'handle_task_creation.worker_task',
                          default="📋 *Task from {manager_name}:*\n{task}",
                          manager_name=manager_name, task=translated),
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending task to worker={worker_id}: {e}")
        await update.message.reply_text(
            get_text(language, 'handle_task_creation.send_error',
                     default="⚠️ Error sending task to worker."))
        return

    # Confirm to manager
    view_btn = get_text(language, 'handle_task_creation.view_all_button', default="📋 View All Tasks")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(view_btn, callback_data="view_tasks")]
    ])
    await update.message.reply_text(
        get_text(language, 'handle_task_creation.manager_confirmation',
                 default="✅ *Task sent to worker:*\n\"{task}\"",
                 task=task_description),
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    logger.info(f"Task created: id={task_id}, manager={user_id} → worker={worker_id}")


# ============================================
# TASK COMPLETION CALLBACK
# ============================================

async def task_completion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle when worker clicks 'Mark Done' button."""
    query = update.callback_query
    user_id = query.from_user.id

    try:
        task_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.answer("⚠️ Invalid task ID")
        return

    user = user_model.get_by_id(user_id)
    role = manager_model.get_role(user_id) if user else None
    language = user['language'] if user else 'English'

    if role != 'worker':
        await query.answer(
            get_text(language, 'task_completion_callback.not_worker',
                     default="⚠️ Only workers can complete tasks"))
        return

    task = task_model.complete(task_id)
    if not task:
        await query.answer(
            get_text(language, 'task_completion_callback.not_found',
                     default="⚠️ Task not found or already completed"))
        return

    # Update message to show completion
    try:
        await query.edit_message_text(
            get_text(language, 'task_completion_callback.task_completed',
                     default="📋 *Task:*\n{task}\n\n✅ *Completed!*",
                     task=task['description_translated']),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.warning(f"Could not update task message: {e}")

    await query.answer(
        get_text(language, 'task_completion_callback.completion_confirmation',
                 default="✅ Task marked as completed"))

    # Notify manager
    conn = connection_model.get_by_id(task['connection_id'])
    if conn:
        manager_user = user_model.get_by_id(conn['manager_id'])
        if manager_user:
            worker_name = query.from_user.first_name or "Worker"
            completed_time = task['completed_at'].strftime('%H:%M') if task.get('completed_at') else 'now'
            try:
                await context.bot.send_message(
                    chat_id=conn['manager_id'],
                    text=get_text(manager_user['language'], 'task_completion_callback.manager_notification',
                                  default="✅ *Task completed by {worker_name}:*\n\"{task}\"\n\n🕐 Completed at: {time}",
                                  worker_name=worker_name, task=task['description'], time=completed_time),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not notify manager about task completion: {e}")

    logger.info(f"Task completed: id={task_id} by worker={user_id}")


# ============================================
# VIEW TASKS CALLBACK
# ============================================

async def view_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'View All Tasks' button from task creation."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    user = user_model.get_by_id(user_id)
    role = manager_model.get_role(user_id) if user else None
    language = user['language'] if user else 'English'

    if role != 'manager':
        await query.edit_message_text(
            get_text(language, 'view_tasks_callback.not_manager',
                     default="⚠️ Only managers can view tasks."))
        return

    pending = task_model.get_manager_tasks(user_id, status='pending')
    completed = task_model.get_manager_tasks(user_id, status='completed', limit_hours=24)

    if not pending and not completed:
        await query.edit_message_text(
            get_text(language, 'view_tasks_callback.no_other_tasks',
                     default="📋 *Your Tasks*\n\nNo other tasks yet.\n\nCreate more tasks by sending messages starting with **"),
            parse_mode='Markdown')
        return

    response = get_text(language, 'tasks.manager.title', default="📋 *Your Tasks*\n\n")

    if pending:
        response += get_text(language, 'tasks.manager.pending_header',
                             default="⏳ *PENDING ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(pending))
        for t in pending:
            time_str = t['created_at'].strftime('%H:%M') if t.get('created_at') else 'Unknown'
            response += get_text(language, 'tasks.manager.task_item',
                                 default="• {description}\n  _Created: Today at {time}_\n\n",
                                 description=t['description'], time=time_str)

    if completed:
        response += get_text(language, 'tasks.manager.completed_header',
                             default="\n✅ *COMPLETED TODAY ({count})*\n━━━━━━━━━━━━━━━━━━━━━━━━\n",
                             count=len(completed))
        for t in completed:
            time_str = t['completed_at'].strftime('%H:%M') if t.get('completed_at') else 'Unknown'
            response += get_text(language, 'tasks.manager.completed_item',
                                 default="• {description}\n  _Completed at {time}_\n\n",
                                 description=t['description'], time=time_str)

    await query.edit_message_text(response, parse_mode='Markdown')
