from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import BOT_NAME
from utils.translations import get_text
from database.credits_client import (
    get_user_credits, add_user_credits, deduct_user_credits, 
    get_credit_packages, get_package_by_id, purchase_credits,
    get_user_credit_stats
)
from utils.credit_analytics import (
    generate_credit_usage_chart, generate_usage_breakdown_chart, 
    get_credit_usage_breakdown, predict_credit_depletion
)
import matplotlib
matplotlib.use('Agg')  # Required for operation without a graphical interface

from database.credits_client import add_stars_payment_option, get_stars_conversion_rate

# Function moved from menu_handler.py to avoid circular import
def get_user_language(context, user_id):
    """
    Get the user's language from context or database
    
    Args:
        context: Bot context
        user_id: User ID
        
    Returns:
        str: Language code (pl, en, ru)
    """
    # Check if language is saved in context
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data'] and 'language' in context.chat_data['user_data'][user_id]:
        return context.chat_data['user_data'][user_id]['language']
    
    # If not, get from database
    try:
        from database.supabase_client import supabase
        response = supabase.table('users').select('language').eq('id', user_id).execute()
        
        if response.data and response.data[0].get('language'):
            # Save in context for future use
            if 'user_data' not in context.chat_data:
                context.chat_data['user_data'] = {}
            
            if user_id not in context.chat_data['user_data']:
                context.chat_data['user_data'][user_id] = {}
            
            context.chat_data['user_data'][user_id]['language'] = response.data[0]['language']
            return response.data[0]['language']
    except Exception as e:
        print(f"Error getting language from database: {e}")
    
    # Default language if not found in database
    return "pl"

async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /credits command
    Display information about user's credits
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    credits = get_user_credits(user_id)
    
    # Create buttons for credits
    keyboard = [
        [
            InlineKeyboardButton(get_text("buy_credits_btn", language), callback_data="menu_credits_buy"),
            InlineKeyboardButton(get_text("payment_methods", language, default="Metody płatności"), callback_data="payment_command")
        ],
        [
            InlineKeyboardButton(get_text("credit_stats", language), callback_data="credit_advanced_analytics"),
            InlineKeyboardButton(get_text("subscription_manage", language, default="Subskrypcje"), callback_data="subscription_command")
        ],
        [
            InlineKeyboardButton(get_text("transaction_history", language, default="Historia transakcji"), callback_data="transactions_command")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send credit information
    await update.message.reply_text(
        get_text("credits_info", language, bot_name=BOT_NAME, credits=credits),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /buy command
    Directs users to payment options
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Check if stars option is specified
    if context.args and len(context.args) > 0 and context.args[0].lower() == "stars":
        await show_stars_purchase_options(update, context)
        return
    
    # For other purchase options, show payment methods
    from handlers.payment_handler import payment_command
    await payment_command(update, context)

async def handle_credit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle buttons related to credits
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()
    
    # Route to payment handler if it's a payment-related command
    if query.data == "payment_command" or query.data.startswith("payment_method_") or \
       query.data.startswith("buy_package_") or query.data == "subscription_command" or \
       query.data.startswith("cancel_subscription_") or query.data.startswith("confirm_cancel_sub_") or \
       query.data == "transactions_command":
        try:
            from handlers.payment_handler import handle_payment_callback
            result = await handle_payment_callback(update, context)
            if result:
                return True
        except Exception as e:
            print(f"Error routing to payment handler: {e}")
            import traceback
            traceback.print_exc()
    
    # Handle credits check
    if query.data == "credits_check" or query.data == "menu_credits_check":
        # Get current credit data
        credits = get_user_credits(user_id)
        credit_stats = get_user_credit_stats(user_id)
        
        # Prepare message text
        message = f"""
*{get_text('credits_management', language)}*

{get_text('current_balance', language)}: *{credits}* {get_text('credits', language)}

{get_text('total_purchased', language)}: *{credit_stats.get('total_purchased', 0)}* {get_text('credits', language)}
{get_text('total_spent', language)}: *{credit_stats.get('total_spent', 0):.2f}* PLN
{get_text('last_purchase', language)}: *{credit_stats.get('last_purchase', get_text('no_transactions', language))}*

*{get_text('credit_history', language)} ({get_text('last_10', language, default='last 10')}):*
"""
        
        if credit_stats.get('usage_history'):
            for i, transaction in enumerate(credit_stats['usage_history'], 1):
                date = transaction['date'].split('T')[0]
                if transaction['type'] in ["add", "purchase", "subscription", "subscription_renewal"]:
                    message += f"\n{i}. ➕ +{transaction['amount']} {get_text('credits', language)} ({date})"
                else:
                    message += f"\n{i}. ➖ -{transaction['amount']} {get_text('credits', language)} ({date})"
                if transaction.get('description'):
                    message += f" - {transaction['description']}"
        else:
            message += f"\n{get_text('no_transactions', language)}"
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton(get_text("buy_more_credits", language), callback_data="menu_credits_buy")],
            [InlineKeyboardButton(get_text("credit_stats", language), callback_data="credit_advanced_analytics")],
            [InlineKeyboardButton(get_text("back", language), callback_data="menu_section_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Update message
        try:
            await query.edit_message_text(
                message, 
                reply_markup=reply_markup, 
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error updating message: {e}")
        return True
    
    # Handle credit purchase options
    if query.data == "credits_buy" or query.data == "menu_credits_buy":
        # Redirect to payment methods
        from handlers.payment_handler import handle_payment_callback
        
        # Create a mock callback query for payment_command
        query.data = "payment_command"
        return await handle_payment_callback(update, context)
    
    # Handle advanced credit analytics
    if query.data == "credits_stats" or query.data == "credit_advanced_analytics":
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Inform user that analysis is starting
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption="⏳ Analyzing credit usage data..."
            )
        else:
            await query.edit_message_text(
                text="⏳ Analyzing credit usage data..."
            )
        
        # Default number of days for analysis
        days = 30
        
        # Get credit depletion forecast
        depletion_info = predict_credit_depletion(user_id, days)
        
        if not depletion_info:
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption="You don't have enough credit usage history to perform analysis. Try again after performing several operations."
                )
            else:
                await query.edit_message_text(
                    text="You don't have enough credit usage history to perform analysis. Try again after performing several operations."
                )
            return True
        
        # Prepare analysis message
        message = f"📊 *{get_text('credit_analytics', language, default='Analiza wykorzystania kredytów')}*\n\n"
        message += f"{get_text('current_balance', language)}: *{depletion_info['current_balance']}* {get_text('credits', language)}\n"
        message += f"{get_text('average_daily_usage', language, default='Średnie dzienne zużycie')}: *{depletion_info['average_daily_usage']}* {get_text('credits', language)}\n"
        
        if depletion_info['days_left']:
            message += f"{get_text('predicted_depletion', language, default='Przewidywane wyczerpanie kredytów')}: {get_text('in_days', language, default='za')} *{depletion_info['days_left']}* {get_text('days', language, default='dni')} "
            message += f"({depletion_info['depletion_date']})\n\n"
        else:
            message += f"{get_text('not_enough_data', language, default='Za mało danych, aby przewidzieć wyczerpanie kredytów.')}.\n\n"
        
        # Get credit usage breakdown
        usage_breakdown = get_credit_usage_breakdown(user_id, days)
        
        if usage_breakdown:
            message += f"*{get_text('usage_breakdown', language, default='Rozkład zużycia kredytów')}:*\n"
            for category, amount in usage_breakdown.items():
                percentage = amount / sum(usage_breakdown.values()) * 100
                message += f"- {category}: *{amount}* {get_text('credits', language)} ({percentage:.1f}%)\n"
        
        # Update message with analysis
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=message,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Generate and send charts
        # Usage history chart
        usage_chart = generate_credit_usage_chart(user_id, days)
        if usage_chart:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=usage_chart,
                caption=f"📈 {get_text('usage_history_chart', language, default=f'Historia wykorzystania kredytów z ostatnich {days} dni')}"
            )
        
        # Usage breakdown chart
        breakdown_chart = generate_usage_breakdown_chart(user_id, days)
        if breakdown_chart:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=breakdown_chart,
                caption=f"📊 {get_text('usage_breakdown_chart', language, default=f'Rozkład wykorzystania kredytów z ostatnich {days} dni')}"
            )
        
        # Add back button
        keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_credits_check")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Update message with back button
        try:
            if hasattr(query.message, 'caption'):
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            else:
                await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            print(f"Error updating keyboard: {e}")
        
        return True

    # Handle Telegram stars purchase options
    if query.data == "show_stars_options":
        # Get star exchange rates
        conversion_rates = get_stars_conversion_rate()
        
        # Create keyboard
        keyboard = []
        for stars, credits in conversion_rates.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"⭐ {stars} {get_text('stars', language, default='gwiazdek')} = {credits} {get_text('credits', language)}", 
                    callback_data=f"buy_stars_{stars}"
                )
            ])
        
        # Add back button
        keyboard.append([
            InlineKeyboardButton(get_text("back", language), callback_data="credits_buy")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            get_text("stars_purchase_info", language, default="🌟 *Zakup kredytów za Telegram Stars* 🌟\n\nWybierz jedną z opcji poniżej, aby wymienić gwiazdki Telegram na kredyty.\nIm więcej gwiazdek wymienisz jednorazowo, tym lepszy bonus otrzymasz!\n\n⚠️ *Uwaga:* Aby dokonać zakupu gwiazdkami, wymagane jest konto Telegram Premium."),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return True
    
    # Handle stars purchase
    if query.data.startswith("buy_stars_"):
        stars_amount = int(query.data.split("_")[2])
        
        # Get star exchange rates
        conversion_rates = get_stars_conversion_rate()
        
        # Check if this stars amount is supported
        if stars_amount not in conversion_rates:
            await query.edit_message_text(
                get_text("stars_invalid_amount", language, default="Wystąpił błąd. Nieprawidłowa liczba gwiazdek."),
                parse_mode=ParseMode.MARKDOWN
            )
            return True
        
        credits_amount = conversion_rates[stars_amount]
        
        # Add credits to user's account
        success = add_stars_payment_option(user_id, stars_amount, credits_amount)
        
        if success:
            current_credits = get_user_credits(user_id)
            await query.edit_message_text(
                get_text("stars_purchase_success", language, default=f"✅ *Zakup zakończony sukcesem!*\n\nWymieniono *{stars_amount}* gwiazdek na *{credits_amount}* kredytów\n\nAktualny stan kredytów: *{current_credits}*\n\nDziękujemy za zakup! 🎉"),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                get_text("purchase_error", language, default="Wystąpił błąd podczas realizacji płatności. Spróbuj ponownie później."),
                parse_mode=ParseMode.MARKDOWN
            )
        return True
    
    return False  # If callback not handled

async def credit_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /creditstats command
    Display detailed statistics on user's credits
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    stats = get_user_credit_stats(user_id)
    
    # Format the date of last purchase
    last_purchase = get_text("none", language, default="Brak") if not stats['last_purchase'] else stats['last_purchase'].split('T')[0]
    
    # Create message with statistics
    message = f"""
*📊 {get_text('credit_statistics', language, default='Statystyki kredytów')}*

{get_text('current_balance', language)}: *{stats['credits']}* {get_text('credits', language)}
{get_text('total_purchased', language)}: *{stats['total_purchased']}* {get_text('credits', language)}
{get_text('total_spent', language)}: *{stats['total_spent']}* PLN
{get_text('last_purchase', language)}: *{last_purchase}*

*📝 {get_text('usage_history', language, default='Historia użycia')} ({get_text('last_10', language, default='ostatnie 10 transakcji')}):*
"""
    
    if not stats['usage_history']:
        message += f"\n{get_text('no_transaction_history', language, default='Brak historii transakcji.')}"
    else:
        for i, transaction in enumerate(stats['usage_history']):
            date = transaction['date'].split('T')[0]
            if transaction['type'] in ["add", "purchase", "subscription", "subscription_renewal"]:
                message += f"\n{i+1}. ➕ +{transaction['amount']} {get_text('credits', language)} ({date})"
                if transaction['description']:
                    message += f" - {transaction['description']}"
            else:
                message += f"\n{i+1}. ➖ -{transaction['amount']} {get_text('credits', language)} ({date})"
                if transaction['description']:
                    message += f" - {transaction['description']}"
    
    # Add button to buy credits
    keyboard = [
        [InlineKeyboardButton(get_text("buy_more_credits", language), callback_data="menu_credits_buy")],
        [InlineKeyboardButton(get_text("view_payment_history", language, default="Zobacz historię płatności"), callback_data="transactions_command")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def credit_analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Display credit usage analysis
    Usage: /creditstats [days]
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Check if number of days is specified
    days = 30  # Default 30 days
    if context.args and len(context.args) > 0:
        try:
            days = int(context.args[0])
            # Limit range
            if days < 1:
                days = 1
            elif days > 365:
                days = 365
        except ValueError:
            pass
    
    # Inform user that analysis is starting
    status_message = await update.message.reply_text(
        get_text("analyzing_credit_usage", language, default="⏳ Analizuję dane wykorzystania kredytów...")
    )
    
    # Get credit depletion forecast
    depletion_info = predict_credit_depletion(user_id, days)
    
    if not depletion_info:
        await status_message.edit_text(
            get_text("not_enough_credit_history", language, default="Nie masz wystarczającej historii użycia kredytów, aby przeprowadzić analizę. Spróbuj ponownie po wykonaniu kilku operacji."),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Prepare analysis message
    message = f"📊 *{get_text('credit_analytics', language, default='Analiza wykorzystania kredytów')}*\n\n"
    message += f"{get_text('current_balance', language)}: *{depletion_info['current_balance']}* {get_text('credits', language)}\n"
    message += f"{get_text('average_daily_usage', language, default='Średnie dzienne zużycie')}: *{depletion_info['average_daily_usage']}* {get_text('credits', language)}\n"
    
    if depletion_info['days_left']:
        message += f"{get_text('predicted_depletion', language, default='Przewidywane wyczerpanie kredytów')}: {get_text('in_days', language, default='za')} *{depletion_info['days_left']}* {get_text('days', language, default='dni')} "
        message += f"({depletion_info['depletion_date']})\n\n"
    else:
        message += f"{get_text('not_enough_data', language, default='Za mało danych, aby przewidzieć wyczerpanie kredytów.')}.\n\n"
    
    # Get credit usage breakdown
    usage_breakdown = get_credit_usage_breakdown(user_id, days)
    
    if usage_breakdown:
        message += f"*{get_text('usage_breakdown', language, default='Rozkład zużycia kredytów')}:*\n"
        for category, amount in usage_breakdown.items():
            percentage = amount / sum(usage_breakdown.values()) * 100
            message += f"- {category}: *{amount}* {get_text('credits', language)} ({percentage:.1f}%)\n"
    
    # Send analysis message
    await status_message.edit_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Generate and send usage history chart
    usage_chart = generate_credit_usage_chart(user_id, days)
    
    if usage_chart:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=usage_chart,
            caption=f"📈 {get_text('usage_history_chart', language, default=f'Historia wykorzystania kredytów z ostatnich {days} dni')}"
        )
    
    # Generate and send usage breakdown chart
    breakdown_chart = generate_usage_breakdown_chart(user_id, days)
    
    if breakdown_chart:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=breakdown_chart,
            caption=f"📊 {get_text('usage_breakdown_chart', language, default=f'Rozkład wykorzystania kredytów z ostatnich {days} dni')}"
        )

async def show_stars_purchase_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show options to purchase credits using Telegram stars
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Get conversion rate
    conversion_rates = get_stars_conversion_rate()
    
    # Create buttons for different star purchase options
    keyboard = []
    for stars, credits in conversion_rates.items():
        keyboard.append([
            InlineKeyboardButton(
                f"⭐ {stars} {get_text('stars', language, default='gwiazdek')} = {credits} {get_text('credits', language)}", 
                callback_data=f"buy_stars_{stars}"
            )
        ])
    
    # Add return button
    keyboard.append([
        InlineKeyboardButton(get_text("back_to_purchase_options", language, default="🔙 Powrót do opcji zakupu"), callback_data="buy_credits")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        get_text("stars_purchase_info", language, default="🌟 *Zakup kredytów za Telegram Stars* 🌟\n\nWybierz jedną z opcji poniżej, aby wymienić gwiazdki Telegram na kredyty.\nIm więcej gwiazdek wymienisz jednorazowo, tym lepszy bonus otrzymasz!\n\n⚠️ *Uwaga:* Aby dokonać zakupu gwiazdkami, wymagane jest konto Telegram Premium."),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )