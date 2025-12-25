import json
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import database
import translator
import translation_msg_context
import message_history
import usage_tracker
import subscription_manager
from config import load_config
from datetime import datetime, timezone

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
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    # Check if user already registered
    if user:
        await update.message.reply_text(
            f"Welcome back! You're registered as {user['role']}.\n"
            f"Your language: {user['language']}\n\n"
            f"Use /help to see available commands."
        )
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
    
    await update.message.reply_text(
        "Welcome to BridgeOS! 🌉\n\nSelect your language:",
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
    """User selected gender - check if they have an invite code or ask for industry"""
    context.user_data['gender'] = update.message.text
    
    # Check if user came via deep-link with invite code
    if 'invite_code' in context.user_data:
        code = context.user_data['invite_code']
        user_id = str(update.effective_user.id)
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
            await update.message.reply_text(
                "❌ Invalid invitation code.\n\n"
                "Please ask your contact for a new invitation link.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Check if manager already has a worker
        manager = database.get_user(manager_id)
        if manager.get('worker'):
            await update.message.reply_text(
                "❌ This contact already has a worker connected.\n"
                "Ask them to use /reset first.",
                reply_markup=ReplyKeyboardRemove()
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
            "✅ Connected to your contact! You can start chatting now.\n\n"
            "Use /help to see available commands.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Notify manager
        worker_name = update.effective_user.first_name
        await context.bot.send_message(
            chat_id=manager_id,
            text=f"✅ {worker_name} connected as your worker!"
        )
        
        return ConversationHandler.END
    
    # No invite code - user is registering as manager
    # Ask for industry
    config = load_config()
    industries = config.get('industries', {})
    
    industry_buttons = []
    for key, info in industries.items():
        industry_buttons.append(info['name'])
    
    keyboard = [industry_buttons[i:i+2] for i in range(0, len(industry_buttons), 2)]
    
    await update.message.reply_text(
        "What industry do you work in?\n\nThis helps provide accurate translations of technical terms and workplace-specific language.",
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
        industry_key = 'other'
    
    # Generate code and register as manager
    code = generate_code()
    user_data = {
        'language': language,
        'gender': gender,
        'role': 'manager',
        'industry': industry_key,
        'code': code,
        'worker': None
    }
    database.save_user(user_id, user_data)
    
    # Create deep-link for invitation
    bot_username = "FarmTranslateBot"  # Your bot username
    deep_link = f"https://t.me/{bot_username}?start=invite_{code}"
    
    # Create share button with prefilled message
    share_text = f"🌉 Join BridgeOS!\nChat with me in your language:\n{deep_link}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Send Invitation Now", switch_inline_query=share_text)]
    ])
    
    # Send invitation message with share button
    await update.message.reply_text(
        f"✅ Registration complete!\n\n"
        f"📋 Your invitation code: {code}\n"
        f"🔗 Invitation link:\n{deep_link}\n\n"
        f"👉 Tap the button below to share with your contact:",
        reply_markup=keyboard
    )

    await update.message.reply_text(
        "Ready to start! Use /help anytime.",
        reply_markup=ReplyKeyboardRemove()
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
/daily - Get daily action items
/subscription - View subscription status
/refer - Recommend to other managers
/reset - Delete account and start over

💬 *How to use:*
Just type your message and it will be automatically translated and sent to your contact!
        """
    else:
        help_text = """
📋 *Available Commands:*

/help - Show this help message
/refer - Recommend to other managers
/reset - Delete account

💬 *How to use:*
Just type your message and it will be automatically translated and sent to your contact!
        """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def mycode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show manager's code with share button"""
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
    
    # Create deep-link for invitation
    bot_username = "FarmTranslateBot"  # Your bot username
    deep_link = f"https://t.me/{bot_username}?start=invite_{code}"
    
    # Create share button with prefilled message
    share_text = f"🌉 Join BridgeOS!\nChat with me in your language:\n{deep_link}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Invitation", switch_inline_query=share_text)]
    ])
    
    # Send status and invitation
    await update.message.reply_text(
        f"👥 Worker connected: {'Yes ✅' if has_worker else 'No ❌'}\n\n"
        f"📋 Your invitation code: {code}\n"
        f"🔗 Invitation link:\n{deep_link}\n\n"
        f"👉 Tap the button below to share with your contact:",
        reply_markup=keyboard
    )

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let users share the bot with other managers/colleagues"""
    
    # Load config for dynamic language count
    config = load_config()
    language_count = len(config.get('languages', []))
    
    # Shareable message for other potential managers
    share_text = (
        "🌉 Check out BridgeOS!\n\n"
        "I use it to communicate with my team in real-time - "
        "we speak different languages but chat naturally!\n\n"
        f"🌍 {language_count} languages supported\n"  # ← Dynamic!
        "✅ Instant translation\n"
        "🏭 Industry-specific terms\n"
        "💬 Simple & effective\n\n"
        "Try it free: https://t.me/FarmTranslateBot"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Recommend BridgeOS", switch_inline_query=share_text)]
    ])
    
    await update.message.reply_text(
        "🌉 Love BridgeOS?\n\n"
        "Help other managers break language barriers!\n\n"
        "Recommend BridgeOS to colleagues, friends, or anyone "
        "who manages teams speaking different languages.\n\n"
        "👉 Tap the button to share:",
        reply_markup=keyboard
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user account - delete all data and allow re-registration"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("You don't have an account to reset.")
        return
    
    if user['role'] == 'manager':
        worker_id = user.get('worker')
        if worker_id:
            worker = database.get_user(worker_id)
            if worker:
                translation_msg_context.clear_conversation(user_id, worker_id)
                
                all_users = database.get_all_users()
                if worker_id in all_users:
                    del all_users[worker_id]
                    database.save_data(all_users)
                
                try:
                    await context.bot.send_message(
                        chat_id=worker_id,
                        text="⚠️ Your contact has reset their account.\n"
                             "Your account has also been reset.\n\n"
                             "You'll need a new invitation to reconnect."
                    )
                except Exception:
                    pass
    
    elif user['role'] == 'worker':
        manager_id = user.get('manager')
        if manager_id:
            manager = database.get_user(manager_id)
            if manager:
                manager['worker'] = None
                database.save_user(manager_id, manager)
                
                try:
                    worker_name = update.effective_user.first_name
                    await context.bot.send_message(
                        chat_id=manager_id,
                        text=f"ℹ️ {worker_name} has reset their account and is no longer connected."
                    )
                except Exception:
                    pass
            
            translation_msg_context.clear_conversation(user_id, manager_id)
    
    all_users = database.get_all_users()
    if user_id in all_users:
        del all_users[user_id]
        database.save_data(all_users)
    
    await update.message.reply_text(
        "✅ Your account has been reset!\n\n"
        "All your data and connections have been deleted.\n"
        "Use /start to register again."
    )




async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI-powered Action itesms of last 24 hours"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    # Only managers can get summaries
    if user['role'] != 'manager':
        await update.message.reply_text(
            "Only managers can generate summaries.\n\n"
            "This feature helps managers track action items and tasks."
        )
        return
    
    # Check if manager has a worker
    worker_id = user.get('worker')
    if not worker_id:
        await update.message.reply_text(
            "You don't have a worker connected yet.\n\n"
            "Connect with a worker first to see conversation summaries."
        )
        return
    
    # Send "generating" message
    generating_msg = await update.message.reply_text(
        "⏳ Generating Daily Action Items (Last 24 Hours)...\n\n"
        "Analyzing last 24 hours of conversation."
    )
    
    try:
        # Get messages from last 24 hours
        messages = message_history.get_messages(
            user_id_1=user_id,
            user_id_2=worker_id,
            hours=24
        )
        
        # Get industry context
        industry_key = user.get('industry', 'other')
        
        # Generate daily action items using Claude
        action_items_text = translator.generate_daily_actionitems(messages, industry=industry_key)
        
        # Count total messages
        message_count = len(messages)
        
        # Format response
        response = f"📋 *Daily Action Items (Last 24 Hours)*\n\n{action_items_text}"
        
        # Add message count if there are messages
        if message_count > 0:
            response += f"\n\n_Total messages: {message_count}_"
        
        # Delete "generating" message
        await generating_msg.delete()
        
        # Send daily action items
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        # Delete "generating" message
        await generating_msg.delete()
        
        # Send error message
        await update.message.reply_text(
            f"âŒ Error generating daily action items: {str(e)}\n\n"
            f"Please try again later or contact support."
        )


async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription status and management"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    if user['role'] != 'manager':
        await update.message.reply_text(
            "Workers have unlimited messages! 🎉\n\n"
            "Only managers need subscriptions.",
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
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🏢 Upgrade to Business License (${monthly_price:.0f}/month)", url=checkout_url)
        ]])
        
        await update.message.reply_text(
            f"📋 *Subscription Status*\n\n"
            f"Status: ❌ No Active Subscription\n"
            f"Messages Used: {messages_sent} / {free_limit} (Free Tier)\n\n"
            f"💳 *Subscribe to BridgeOS:*\n"
            f"• Unlimited messages\n"
            f"• ${monthly_price:.0f}/month\n"
            f"• Cancel anytime",
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
        
        message = f"📋 *Your Subscription*\n\n" \
                  f"{status_emoji} Status: {status.title()}\n" \
                  f"💳 Plan: Unlimited Messages\n" \
                  f"💵 Price: ${monthly_price:.0f}/month\n"
        
        if status == 'active':
            message += f"📅 Renews: {renews_at}\n"
        elif status == 'cancelled' and ends_at:
            message += f"📅 Access Until: {ends_at[:10]}\n"
        
        message += "\n_Manage or cancel anytime._"
        
        if portal_url:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ Manage Business License", url=portal_url)
            ]])
            await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')

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
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"🏢 Upgrade to Business License (${monthly_price:.0f}/month)", url=checkout_url)
                ]])
                
                await update.message.reply_text(
                    f"⚠️ *Free Plan Limit Reached*\n\n"
                    f"Your business has used its allocation of {free_limit} translated messages.\n"
                    f"To continue operations without interruption, "
                    f"please upgrade your account to the *Business License*.\n\n"
                    f"*BridgeOS Business License:*\n"
                    f"✅ Full Business Access (Unlimited usage)\n" 
                    f"✅ Manager Dashboard\n"
                    f"✅ Priority Processing\n"
                    f"✅ Industry-Specific Translations\n"
                    f"✅ Multi-Language Support (12 languages)\n"
                    f"• *Price:* ${monthly_price:.0f}/month (Cancel anytime)\n\n"                    
                    f"Tap below to upgrade:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                return
    
    text = update.message.text
    user_lang = user['language']
    
    translation_context_size = config.get('translation_context_size', 5)
    max_history_messages = translation_context_size * 2
    
    if user['role'] == 'manager':
        worker_id = user.get('worker')
        if not worker_id:
            await update.message.reply_text(
                "⚠️ You don't have a contact connected yet.\n"
                "Share your invitation (use /mycode) with your contact."
            )
            return
        
        worker = database.get_user(worker_id)
        if not worker:
            await update.message.reply_text(
                "⚠️ Your contact's account no longer exists.\n"
                "Use /reset to start over."
            )
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
        await context.bot.send_message(
            chat_id=worker_id,
            text=f"🗣️ From {manager_name}: {translated}"
        )
        
        # Increment message counter for manager (after successful send)
        # Only increment if user doesn't have subscription
        if not subscription_manager.is_subscribed(telegram_id):
            allowed = usage_tracker.increment_message_count(telegram_id)
            
            if not allowed:
                # Just hit the limit - show subscribe button
                checkout_url = subscription_manager.create_checkout_url(telegram_id)
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"🏢 Upgrade to Business License (${monthly_price:.0f}/month)", url=checkout_url)
                ]])
                
                await update.message.reply_text(
                    f"⚠️ *That was your last free message!*\n\n"
                    f"You've used all {free_limit} free messages.\n\n"
                    f"💳 Subscribe for unlimited messages (${monthly_price:.0f}/month):",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
    
    elif user['role'] == 'worker':
        manager_id = user.get('manager')
        if not manager_id:
            await update.message.reply_text(
                "⚠️ You're not connected to a contact.\n"
                "Ask your contact for their invitation link."
            )
            return
        
        manager = database.get_user(manager_id)
        if not manager:
            await update.message.reply_text(
                "⚠️ Your contact's account no longer exists.\n"
                "Use /reset and wait for a new invitation."
            )
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
        await context.bot.send_message(
            chat_id=manager_id,
            text=f"🗣️ From {sender_name}: {translated}"
        )

# ============================================
# MEDIA HANDLING
# ============================================

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward non-text messages (photos, videos, voice, files, etc.) as-is"""
    user_id = str(update.effective_user.id)
    user = database.get_user(user_id)
    
    if not user:
        await update.message.reply_text("Please use /start to register first.")
        return
    
    # Determine recipient based on role
    if user['role'] == 'manager':
        recipient_id = user.get('worker')
        if not recipient_id:
            await update.message.reply_text(
                "⚠️ You don't have a contact connected yet.\n"
                "Share your invitation (use /mycode) with your contact."
            )
            return
        sender_name = update.effective_user.first_name
        prefix = f"📎 From {sender_name}:"
    
    elif user['role'] == 'worker':
        recipient_id = user.get('manager')
        if not recipient_id:
            await update.message.reply_text(
                "⚠️ You're not connected to a contact.\n"
                "Ask your contact for their invitation link."
            )
            return
        sender_name = update.effective_user.first_name
        prefix = f"📎 From {sender_name}:"
    
    # Check if recipient exists
    recipient = database.get_user(recipient_id)
    if not recipient:
        await update.message.reply_text(
            "⚠️ Your contact's account no longer exists.\n"
            "Use /reset to start over."
        )
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
    app.add_handler(CommandHandler('mycode', mycode_command))
    app.add_handler(CommandHandler('refer', refer_command))
    app.add_handler(CommandHandler('daily', daily_command))
    app.add_handler(CommandHandler('subscription', subscription_command))
    app.add_handler(CommandHandler('reset', reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Handle all media types (photos, videos, voice, files, stickers, etc.)
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO | 
         filters.Document.ALL | filters.LOCATION | filters.CONTACT | filters.Sticker.ALL),
        handle_media
    ))
    
    print("🤖 BridgeOS bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()