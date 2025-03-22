from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import CHAT_MODES
from utils.translations import get_text
from database.credits_client import get_user_credits
from utils.user_utils import mark_chat_initialized
from database.supabase_client import create_new_conversation

def get_user_language(context, user_id):
    """Pomocnicza funkcja do pobierania języka użytkownika"""
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data'] and 'language' in context.chat_data['user_data'][user_id]:
        return context.chat_data['user_data'][user_id]['language']
    return "pl"  # Domyślny język

async def show_modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pokazuje dostępne tryby czatu"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy użytkownik ma kredyty
    credits = get_user_credits(user_id)
    if credits <= 0:
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    # Utwórz przyciski dla dostępnych trybów
    keyboard = []
    for mode_id, mode_info in CHAT_MODES.items():
        # Pobierz przetłumaczoną nazwę trybu
        mode_name = get_text(f"chat_mode_{mode_id}", language, default=mode_info['name'])
        # Pobierz przetłumaczony tekst dla kredytów
        credit_text = get_text("credit", language, default="kredyt")
        if mode_info['credit_cost'] != 1:
            credit_text = get_text("credits", language, default="kredytów")
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{mode_name} ({mode_info['credit_cost']} {credit_text})", 
                callback_data=f"mode_{mode_id}"
            )
        ])
    
    # Dodaj przycisk powrotu do menu
    keyboard.append([
        InlineKeyboardButton(get_text("back", language, default="Powrót"), callback_data="menu_back_main")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        get_text("select_chat_mode", language, default="Wybierz tryb czatu:"),
        reply_markup=reply_markup
    )

async def handle_mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, mode_id):
    """Obsługuje wybór trybu czatu z ulepszoną wizualizacją"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    print(f"Obsługiwanie wyboru trybu: {mode_id}")
    
    # Sprawdź, czy tryb istnieje
    if mode_id not in CHAT_MODES:
        try:
            await query.answer(get_text("mode_not_available", language, default="Wybrany tryb nie jest dostępny."))
            
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("mode_not_available", language, default="Wybrany tryb nie jest dostępny."),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("mode_not_available", language, default="Wybrany tryb nie jest dostępny."),
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            print(f"Błąd przy edycji wiadomości: {e}")
        return
    
    # Zapisz wybrany tryb w kontekście użytkownika
    if 'user_data' not in context.chat_data:
        context.chat_data['user_data'] = {}
    
    if user_id not in context.chat_data['user_data']:
        context.chat_data['user_data'][user_id] = {}
    
    context.chat_data['user_data'][user_id]['current_mode'] = mode_id
    
    # Jeśli tryb ma określony model, ustaw go również
    if "model" in CHAT_MODES[mode_id]:
        context.chat_data['user_data'][user_id]['current_model'] = CHAT_MODES[mode_id]["model"]
    
    # Pobierz przetłumaczoną nazwę trybu i inne informacje
    mode_name = get_text(f"chat_mode_{mode_id}", language, default=CHAT_MODES[mode_id]["name"])
    prompt_key = f"prompt_{mode_id}"
    mode_description = get_text(prompt_key, language, default=CHAT_MODES[mode_id]["prompt"])
    credit_cost = CHAT_MODES[mode_id]["credit_cost"]
    model_name = AVAILABLE_MODELS.get(CHAT_MODES[mode_id].get("model", DEFAULT_MODEL), "Model standardowy")
    
    # Skróć opis, jeśli jest zbyt długi
    if len(mode_description) > 200:
        short_description = mode_description[:197] + "..."
    else:
        short_description = mode_description
    
    try:
        # Use enhanced formatting with visual card
        from utils.message_formatter_enhanced import format_mode_selection
        message_text = format_mode_selection(mode_name, short_description, credit_cost, model_name)
        
        # Add tip about mode usage if appropriate
        from utils.tips import should_show_tip, get_random_tip
        if should_show_tip(user_id, context):
            tip = get_random_tip('general')
            message_text += f"\n\n💡 *Porada:* {tip}"
        
        # Dodaj przyciski powrotu do menu trybów
        keyboard = [
            [InlineKeyboardButton("✏️ " + get_text("start_chat", language, default="Rozpocznij rozmowę"), callback_data="quick_new_chat")],
            [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_section_chat_modes")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Sprawdź typ wiadomości i użyj odpowiedniej metody
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Błąd przy edycji wiadomości: {e}")
        try:
            # Bez formatowania Markdown
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=message_text.replace('*', ''),
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text(
                    text=message_text.replace('*', ''),
                    reply_markup=reply_markup
                )
        except Exception as e2:
            print(f"Drugi błąd przy edycji wiadomości: {e2}")
        
    # Utwórz nową konwersację dla wybranego trybu
    from database.supabase_client import create_new_conversation
    create_new_conversation(user_id)
    
    # Mark chat as initialized
    from utils.user_utils import mark_chat_initialized
    mark_chat_initialized(context, user_id)