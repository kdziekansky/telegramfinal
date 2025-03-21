import os
# Wyłącz wszystkie ustawienia proxy
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ["HTTPX_SKIP_PROXY"] = "true"

import logging
logging.basicConfig(level=logging.DEBUG)
import re
import datetime
import pytz
from handlers.admin_package_handler import (
    add_package, list_packages, toggle_package, add_default_packages
)
from telegram.ext import Application
from config import TELEGRAM_TOKEN
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ReplyKeyboardRemove
from handlers.help_handler import help_command
from handlers.translate_handler import translate_command
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction
from config import (
    TELEGRAM_TOKEN, DEFAULT_MODEL, AVAILABLE_MODELS, 
    MAX_CONTEXT_MESSAGES, CHAT_MODES, BOT_NAME, CREDIT_COSTS,
    AVAILABLE_LANGUAGES, ADMIN_USER_IDS
)

from handlers.payment_handler import (
    payment_command, subscription_command, handle_payment_callback,
    transactions_command
)

# Import funkcji z modułu tłumaczeń
from utils.translations import get_text

# Import funkcji z modułu sqlite_client
from database.supabase_client import (
    get_or_create_user, create_new_conversation, 
    get_active_conversation, save_message, 
    get_conversation_history, get_message_status,
    check_active_subscription, check_message_limit,
    increment_messages_used
)

# Import funkcji obsługi kredytów
from database.credits_client import (
    get_user_credits, add_user_credits, deduct_user_credits, 
    check_user_credits
)

# Import handlerów kredytów
from handlers.credit_handler import (
    credits_command, buy_command, handle_credit_callback,
    credit_stats_command, credit_analytics_command
)

# Import handlerów kodu aktywacyjnego
from handlers.code_handler import (
    code_command, admin_generate_code
)

# Import handlerów menu
from handlers.menu_handler import (
    handle_menu_callback, set_user_name, get_user_language, store_menu_state
)

# Import handlera start
from handlers.start_handler import (
    start_command, handle_language_selection, language_command
)

# Import handlera obrazów
from handlers.image_handler import generate_image

# Import handlera mode
from handlers.mode_handler import handle_mode_selection, show_modes

from utils.openai_client import (
    chat_completion_stream, prepare_messages_from_history,
    generate_image_dall_e, analyze_document, analyze_image
)

# Import handlera eksportu
from handlers.export_handler import export_conversation
from utils.credit_analytics import generate_credit_usage_chart, generate_usage_breakdown_chart

# Napraw problem z proxy w httpx
from telegram.request import HTTPXRequest

# Nadpisz metodę _build_client
original_build_client = HTTPXRequest._build_client

def patched_build_client(self):
    if hasattr(self, '_client_kwargs') and 'proxies' in self._client_kwargs:
        del self._client_kwargs['proxies']
    return original_build_client(self)

# Podmieniamy metodę
HTTPXRequest._build_client = patched_build_client

# Inicjalizacja aplikacji
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def handle_callback_error(query, error_message, full_error=None):
    """
    Obsługuje błędy podczas przetwarzania callbacków
    
    Args:
        query: Obiekt callback_query
        error_message: Krótka wiadomość o błędzie dla użytkownika
        full_error: Pełny tekst błędu do zalogowania (opcjonalnie)
    """
    if full_error:
        print(f"Błąd podczas obsługi callbacku: {full_error}")
        import traceback
        traceback.print_exc()
    
    # Powiadom użytkownika o błędzie przez notyfikację
    try:
        await query.answer(error_message)
    except Exception:
        pass
    
    # Spróbuj zaktualizować wiadomość z informacją o błędzie
    try:
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=f"⚠️ {error_message}\n\nSpróbuj ponownie później.",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                text=f"⚠️ {error_message}\n\nSpróbuj ponownie później.",
                reply_markup=None
            )
    except Exception:
        # Jeśli nie udało się zaktualizować wiadomości, nie rób nic
        pass

# Teraz, w funkcji handle_callback_query, zamień wszystkie bloki try-except 
# na używające tej nowej funkcji pomocniczej. Na przykład:

    # Przykład użycia w obsłudze trybów:
    if query.data.startswith("mode_"):
        try:
            mode_id = query.data[5:]
            from handlers.mode_handler import handle_mode_selection
            await handle_mode_selection(update, context, mode_id)
            return True
        except Exception as e:
            await handle_callback_error(
                query,
                "Wystąpił błąd podczas wyboru trybu czatu.",
                full_error=str(e)
            )
            return True

async def update_message(query, caption_or_text, reply_markup, parse_mode=None):
    """
    Aktualizuje wiadomość, obsługując różne typy wiadomości i błędy
    
    Args:
        query: Obiekt callback_query
        caption_or_text: Treść do aktualizacji
        reply_markup: Klawiatura inline
        parse_mode: Tryb formatowania (opcjonalnie)
    
    Returns:
        bool: True jeśli się powiodło, False w przypadku błędu
    """
    try:
        if hasattr(query.message, 'caption'):
            # Wiadomość ma podpis (jest to zdjęcie lub inny typ mediów)
            if parse_mode:
                await query.edit_message_caption(
                    caption=caption_or_text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                await query.edit_message_caption(
                    caption=caption_or_text,
                    reply_markup=reply_markup
                )
        else:
            # Standardowa wiadomość tekstowa
            if parse_mode:
                await query.edit_message_text(
                    text=caption_or_text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                await query.edit_message_text(
                    text=caption_or_text,
                    reply_markup=reply_markup
                )
        return True
    except Exception as e:
        print(f"Błąd aktualizacji wiadomości: {e}")
        
        # Spróbuj bez formatowania, jeśli był ustawiony tryb formatowania
        if parse_mode:
            try:
                return await update_message(query, caption_or_text, reply_markup, parse_mode=None)
            except Exception as e2:
                print(f"Drugi błąd aktualizacji wiadomości: {e2}")
        
        return False

# Funkcje onboardingu
async def onboarding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Przewodnik po funkcjach bota krok po kroku
    Użycie: /onboarding
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Inicjalizacja stanu onboardingu
    if 'user_data' not in context.chat_data:
        context.chat_data['user_data'] = {}
    
    if user_id not in context.chat_data['user_data']:
        context.chat_data['user_data'][user_id] = {}
    
    context.chat_data['user_data'][user_id]['onboarding_state'] = 0
    
    # Lista kroków onboardingu
    steps = [
        'welcome', 'chat', 'modes', 'images', 'analysis', 
        'credits', 'referral', 'export', 
        'settings', 'finish'
    ]
    
    # Pobierz aktualny krok
    current_step = 0
    step_name = steps[current_step]
    
    # Przygotuj tekst dla aktualnego kroku
    text = get_text(f"onboarding_{step_name}", language, bot_name=BOT_NAME)
    
    # Przygotuj klawiaturę nawigacyjną
    keyboard = []
    row = []
    
    # Na pierwszym kroku tylko przycisk "Dalej"
    row.append(InlineKeyboardButton(
        get_text("onboarding_next", language), 
        callback_data=f"onboarding_next"
    ))
    
    keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Wysyłamy zdjęcie z podpisem dla pierwszego kroku
    await update.message.reply_photo(
        photo=get_onboarding_image_url(step_name),
        caption=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def get_onboarding_image_url(step_name):
    """
    Zwraca URL obrazu dla danego kroku onboardingu
    """
    # Mapowanie kroków do URL obrazów - każdy krok ma unikalny obraz
    images = {
        'welcome': "https://i.imgur.com/kqIj0SC.png",     # Obrazek powitalny
        'chat': "https://i.imgur.com/kqIj0SC.png",        # Obrazek dla czatu z AI
        'modes': "https://i.imgur.com/vyNkgEi.png",       # Obrazek dla trybów czatu
        'images': "https://i.imgur.com/R3rLbNV.png",      # Obrazek dla generowania obrazów
        'analysis': "https://i.imgur.com/ky7MWTk.png",    # Obrazek dla analizy dokumentów
        'credits': "https://i.imgur.com/0SM3Lj0.png",     # Obrazek dla systemu kredytów
        'referral': "https://i.imgur.com/0I1UjLi.png",    # Obrazek dla programu referencyjnego
        'export': "https://i.imgur.com/xyZLjac.png",      # Obrazek dla eksportu
        'settings': "https://i.imgur.com/XUAAxe9.png",    # Obrazek dla ustawień
        'finish': "https://i.imgur.com/bvPAD9a.png"       # Obrazek dla końca onboardingu
    }
    
    # Użyj odpowiedniego obrazka dla danego kroku lub domyślnego, jeśli nie znaleziono
    return images.get(step_name, "https://i.imgur.com/kqIj0SC.png")

async def handle_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obsługuje przyciski nawigacyjne onboardingu
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()  # Odpowiedz na callback, aby usunąć oczekiwanie
    
    # Inicjalizacja stanu onboardingu jeśli nie istnieje
    if 'user_data' not in context.chat_data:
        context.chat_data['user_data'] = {}
    
    if user_id not in context.chat_data['user_data']:
        context.chat_data['user_data'][user_id] = {}
    
    if 'onboarding_state' not in context.chat_data['user_data'][user_id]:
        context.chat_data['user_data'][user_id]['onboarding_state'] = 0
    
    # Pobierz aktualny stan onboardingu
    current_step = context.chat_data['user_data'][user_id]['onboarding_state']
    
    # Lista kroków onboardingu - USUNIĘTE NIEDZIAŁAJĄCE FUNKCJE
    steps = [
        'welcome', 'chat', 'modes', 'images', 'analysis', 
        'credits', 'referral', 'export', 'settings', 'finish'
    ]
    
    # Obsługa przycisków
    if query.data == "onboarding_next":
        # Przejdź do następnego kroku
        next_step = min(current_step + 1, len(steps) - 1)
        context.chat_data['user_data'][user_id]['onboarding_state'] = next_step
        step_name = steps[next_step]
    elif query.data == "onboarding_back":
        # Wróć do poprzedniego kroku
        prev_step = max(0, current_step - 1)
        context.chat_data['user_data'][user_id]['onboarding_state'] = prev_step
        step_name = steps[prev_step]
    elif query.data == "onboarding_finish":
        # Usuń stan onboardingu i zakończ bez wysyłania nowej wiadomości
        if 'onboarding_state' in context.chat_data['user_data'][user_id]:
            del context.chat_data['user_data'][user_id]['onboarding_state']
        
        # NAPRAWIONE: Wyślij powitalną wiadomość bez formatowania Markdown
        welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
        # Usuń potencjalnie problematyczne znaki formatowania
        welcome_text = welcome_text.replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")
        
        # Utwórz klawiaturę menu
        keyboard = [
            [
                InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes"),
                InlineKeyboardButton(get_text("image_generate", language), callback_data="menu_image_generate")
            ],
            [
                InlineKeyboardButton(get_text("menu_credits", language), callback_data="menu_section_credits"),
                InlineKeyboardButton(get_text("menu_dialog_history", language), callback_data="menu_section_history")
            ],
            [
                InlineKeyboardButton(get_text("menu_settings", language), callback_data="menu_section_settings"),
                InlineKeyboardButton(get_text("menu_help", language), callback_data="menu_help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Próba wysłania zwykłej wiadomości tekstowej zamiast zdjęcia
            message = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=welcome_text,
                reply_markup=reply_markup
            )
            
            # Zapisz ID wiadomości menu i stan menu
            from handlers.menu_handler import store_menu_state
            store_menu_state(context, user_id, 'main', message.message_id)
            
            # Usuń poprzednią wiadomość
            await query.message.delete()
        except Exception as e:
            print(f"Błąd przy wysyłaniu wiadomości końcowej onboardingu: {e}")
        return
    else:
        # Nieznany callback
        return
    
    # Pobierz aktualny krok po aktualizacji
    current_step = context.chat_data['user_data'][user_id]['onboarding_state']
    step_name = steps[current_step]
    
    # Przygotuj tekst dla aktualnego kroku
    text = get_text(f"onboarding_{step_name}", language, bot_name=BOT_NAME)
    
    # Przygotuj klawiaturę nawigacyjną
    keyboard = []
    row = []
    
    # Przycisk "Wstecz" jeśli nie jesteśmy na pierwszym kroku
    if current_step > 0:
        row.append(InlineKeyboardButton(
            get_text("onboarding_back", language),
            callback_data="onboarding_back"
        ))
    
    # Przycisk "Dalej" lub "Zakończ" w zależności od kroku
    if current_step < len(steps) - 1:
        row.append(InlineKeyboardButton(
            get_text("onboarding_next", language),
            callback_data="onboarding_next"
        ))
    else:
        row.append(InlineKeyboardButton(
            get_text("onboarding_finish_button", language),
            callback_data="onboarding_finish"
        ))
    
    keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Pobierz URL obrazu dla aktualnego kroku
    image_url = get_onboarding_image_url(step_name)
    
    try:
        # Usuń poprzednią wiadomość i wyślij nową z odpowiednim obrazem
        await query.message.delete()
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=image_url,
            caption=text,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Błąd przy aktualizacji wiadomości onboardingu: {e}")
        try:
            # Jeśli usunięcie i wysłanie nowej wiadomości się nie powiedzie, 
            # próbujemy zaktualizować obecną
            await query.edit_message_caption(
                caption=text,
                reply_markup=reply_markup
            )
        except Exception as e2:
            print(f"Nie udało się zaktualizować wiadomości: {e2}")
                
# Handlers dla podstawowych komend

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obsługa komendy /restart
    Resetuje kontekst bota, pokazuje informacje o bocie i aktualnych ustawieniach użytkownika
    """
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Resetowanie konwersacji - tworzymy nową konwersację i czyścimy kontekst
        conversation = create_new_conversation(user_id)
        
        # Zachowujemy wybrane ustawienia użytkownika (język, model)
        user_data = {}
        if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
            # Pobieramy tylko podstawowe ustawienia, reszta jest resetowana
            old_user_data = context.chat_data['user_data'][user_id]
            if 'language' in old_user_data:
                user_data['language'] = old_user_data['language']
            if 'current_model' in old_user_data:
                user_data['current_model'] = old_user_data['current_model']
            if 'current_mode' in old_user_data:
                user_data['current_mode'] = old_user_data['current_mode']
        
        # Resetujemy dane użytkownika w kontekście i ustawiamy tylko zachowane ustawienia
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        context.chat_data['user_data'][user_id] = user_data
        
        # Pobierz język użytkownika
        language = get_user_language(context, user_id)
        
        # Wyślij potwierdzenie restartu
        restart_message = get_text("restart_command", language)
        
        # Utwórz klawiaturę menu
        keyboard = [
            [
                InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes"),
                InlineKeyboardButton(get_text("image_generate", language), callback_data="menu_image_generate")
            ],
            [
                InlineKeyboardButton(get_text("menu_credits", language), callback_data="menu_section_credits"),
                InlineKeyboardButton(get_text("menu_dialog_history", language), callback_data="menu_section_history")
            ],
            [
                InlineKeyboardButton(get_text("menu_settings", language), callback_data="menu_section_settings"),
                InlineKeyboardButton(get_text("menu_help", language), callback_data="menu_help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Wyślij wiadomość z menu
        try:
            # Używamy welcome_message zamiast main_menu + status
            welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=restart_message + "\n\n" + welcome_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Zapisz ID wiadomości menu i stan menu
            from handlers.menu_handler import store_menu_state
            store_menu_state(context, user_id, 'main', message.message_id)
        except Exception as e:
            print(f"Błąd przy wysyłaniu wiadomości po restarcie: {e}")
            # Próbuj wysłać prostą wiadomość
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=restart_message
                )
            except Exception as e2:
                print(f"Nie udało się wysłać nawet prostej wiadomości: {e2}")
        
    except Exception as e:
        print(f"Błąd w funkcji restart_command: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            # Używamy context.bot.send_message zamiast update.message.reply_text
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=get_text("restart_error", get_user_language(context, update.effective_user.id))
            )
        except Exception as e2:
            print(f"Błąd przy wysyłaniu wiadomości o błędzie: {e2}")


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sprawdza status konta użytkownika
    Użycie: /status
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Pobierz status kredytów
    credits = get_user_credits(user_id)
    
    # Pobranie aktualnego trybu czatu
    current_mode = get_text("no_mode", language)
    current_mode_cost = 1
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_mode' in user_data and user_data['current_mode'] in CHAT_MODES:
            mode_id = user_data['current_mode']
            current_mode = get_text(f"chat_mode_{mode_id}", language, default=CHAT_MODES[mode_id]["name"])
            current_mode_cost = CHAT_MODES[mode_id]["credit_cost"]
    
    # Pobierz aktualny model
    current_model = DEFAULT_MODEL
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_model' in user_data and user_data['current_model'] in AVAILABLE_MODELS:
            current_model = user_data['current_model']
    
    model_name = AVAILABLE_MODELS.get(current_model, "Unknown Model")
    
    # Pobierz status wiadomości
    message_status = get_message_status(user_id)
    
    # Stwórz wiadomość o statusie, używając tłumaczeń
    message = f"""
*{get_text("status_command", language, bot_name=BOT_NAME)}*

{get_text("available_credits", language)}: *{credits}*
{get_text("current_mode", language)}: *{current_mode}* ({get_text("cost", language)}: {current_mode_cost} {get_text("credits_per_message", language)})
{get_text("current_model", language)}: *{model_name}*

{get_text("messages_info", language)}:
- {get_text("messages_used", language)}: *{message_status["messages_used"]}*
- {get_text("messages_limit", language)}: *{message_status["messages_limit"]}*
- {get_text("messages_left", language)}: *{message_status["messages_left"]}*

{get_text("operation_costs", language)}:
- {get_text("standard_message", language)} (GPT-3.5): 1 {get_text("credit", language)}
- {get_text("premium_message", language)} (GPT-4o): 3 {get_text("credits", language)}
- {get_text("expert_message", language)} (GPT-4): 5 {get_text("credits", language)}
- {get_text("dalle_image", language)}: 10-15 {get_text("credits", language)}
- {get_text("document_analysis", language)}: 5 {get_text("credits", language)}
- {get_text("photo_analysis", language)}: 8 {get_text("credits", language)}

{get_text("buy_more_credits", language)}: /buy
"""
    
    # Dodaj przyciski menu dla łatwiejszej nawigacji
    keyboard = [
        [InlineKeyboardButton(get_text("buy_credits_btn", language), callback_data="menu_credits_buy")],
        [InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        print(f"Błąd formatowania w check_status: {e}")
        # Próba wysłania bez formatowania
        await update.message.reply_text(message, reply_markup=reply_markup)

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rozpoczyna nową konwersację"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Utwórz nową konwersację
    conversation = create_new_conversation(user_id)
    
    if conversation:
        await update.message.reply_text(
            get_text("newchat_command", language),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            get_text("new_chat_error", language),
            parse_mode=ParseMode.MARKDOWN
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa wiadomości tekstowych od użytkownika ze strumieniowaniem odpowiedzi"""
    user_id = update.effective_user.id
    user_message = update.message.text
    language = get_user_language(context, user_id)
    
    print(f"Otrzymano wiadomość od użytkownika {user_id}: {user_message}")
    
    # Określ tryb i koszt kredytów
    current_mode = "no_mode"
    credit_cost = 1
    
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_mode' in user_data and user_data['current_mode'] in CHAT_MODES:
            current_mode = user_data['current_mode']
            credit_cost = CHAT_MODES[current_mode]["credit_cost"]
    
    print(f"Tryb: {current_mode}, koszt kredytów: {credit_cost}")
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    has_credits = check_user_credits(user_id, credit_cost)
    print(f"Czy użytkownik ma wystarczająco kredytów: {has_credits}")
    
    if not has_credits:
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    # Pobierz lub utwórz aktywną konwersację
    try:
        conversation = get_active_conversation(user_id)
        conversation_id = conversation['id']
        print(f"Aktywna konwersacja: {conversation_id}")
    except Exception as e:
        print(f"Błąd przy pobieraniu konwersacji: {e}")
        await update.message.reply_text(get_text("conversation_error", language))
        return
    
    # Zapisz wiadomość użytkownika do bazy danych
    try:
        save_message(conversation_id, user_id, user_message, is_from_user=True)
        print("Wiadomość użytkownika zapisana w bazie")
    except Exception as e:
        print(f"Błąd przy zapisie wiadomości użytkownika: {e}")
    
    # Wyślij informację, że bot pisze
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    # Pobierz historię konwersacji
    try:
        history = get_conversation_history(conversation_id, limit=MAX_CONTEXT_MESSAGES)
        print(f"Pobrano historię konwersacji, liczba wiadomości: {len(history)}")
    except Exception as e:
        print(f"Błąd przy pobieraniu historii: {e}")
        history = []
    
    # Określ model do użycia - domyślny lub z trybu czatu
    model_to_use = CHAT_MODES[current_mode].get("model", DEFAULT_MODEL)
    
    # Jeśli użytkownik wybrał konkretny model, użyj go
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_model' in user_data:
            model_to_use = user_data['current_model']
            # Aktualizuj koszt kredytów na podstawie modelu
            credit_cost = CREDIT_COSTS["message"].get(model_to_use, CREDIT_COSTS["message"]["default"])
    
    print(f"Używany model: {model_to_use}")
    
    # Przygotuj system prompt z wybranego trybu
    system_prompt = CHAT_MODES[current_mode]["prompt"]
    
    # Przygotuj wiadomości dla API OpenAI
    messages = prepare_messages_from_history(history, user_message, system_prompt)
    print(f"Przygotowano {len(messages)} wiadomości dla API")
    
    # Wyślij początkową pustą wiadomość, którą będziemy aktualizować
    response_message = await update.message.reply_text(get_text("generating_response", language))
    
    # Zainicjuj pełną odpowiedź
    full_response = ""
    buffer = ""
    last_update = datetime.datetime.now().timestamp()
    
    # Spróbuj wygenerować odpowiedź
    try:
        print("Rozpoczynam generowanie odpowiedzi strumieniowej...")
        # Generuj odpowiedź strumieniowo
        async for chunk in chat_completion_stream(messages, model=model_to_use):
            full_response += chunk
            buffer += chunk
            
            # Aktualizuj wiadomość co 1 sekundę lub gdy bufor jest wystarczająco duży
            current_time = datetime.datetime.now().timestamp()
            if current_time - last_update >= 1.0 or len(buffer) > 100:
                try:
                    # Dodaj migający kursor na końcu wiadomości
                    await response_message.edit_text(full_response + "▌", parse_mode=ParseMode.MARKDOWN)
                    buffer = ""
                    last_update = current_time
                except Exception as e:
                    # Jeśli wystąpi błąd (np. wiadomość nie została zmieniona), kontynuuj
                    print(f"Błąd przy aktualizacji wiadomości: {e}")
        
        print("Zakończono generowanie odpowiedzi")
        
        # Aktualizuj wiadomość z pełną odpowiedzią bez kursora
        try:
            await response_message.edit_text(full_response, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            # Jeśli wystąpi błąd formatowania Markdown, wyślij bez formatowania
            print(f"Błąd formatowania Markdown: {e}")
            await response_message.edit_text(full_response)
        
        # Zapisz odpowiedź do bazy danych
        save_message(conversation_id, user_id, full_response, is_from_user=False, model_used=model_to_use)
        
        # Odejmij kredyty
        deduct_user_credits(user_id, credit_cost, get_text("message_model", language, model=model_to_use, default=f"Wiadomość ({model_to_use})"))
        print(f"Odjęto {credit_cost} kredytów za wiadomość")
    except Exception as e:
        print(f"Wystąpił błąd podczas generowania odpowiedzi: {e}")
        await response_message.edit_text(get_text("response_error", language, error=str(e)))
        return
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        # Dodaj przycisk doładowania kredytów
        keyboard = [[InlineKeyboardButton(get_text("buy_credits_btn_with_icon", language, default="🛒 Kup kredyty"), callback_data="menu_credits_buy")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Zwiększ licznik wykorzystanych wiadomości
    increment_messages_used(user_id)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa przesłanych dokumentów"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    credit_cost = CREDIT_COSTS["document"]
    if not check_user_credits(user_id, credit_cost):
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    document = update.message.document
    file_name = document.file_name
    
    # Sprawdź rozmiar pliku (limit 25MB)
    if document.file_size > 25 * 1024 * 1024:
        await update.message.reply_text(get_text("file_too_large", language))
        return
    
    # Sprawdź, czy to jest prośba o tłumaczenie
    caption = update.message.caption or ""
    translate_mode = False
    
    if caption.lower().startswith("/translate") or caption.lower().startswith("przetłumacz"):
        translate_mode = True
    
    # Sprawdź, czy plik to PDF i czy jest w trybie tłumaczenia
    is_pdf = file_name.lower().endswith('.pdf')
    
    # Pobierz plik
    if translate_mode and is_pdf:
        from handlers.pdf_handler import handle_pdf_translation
        await handle_pdf_translation(update, context)
        return
    elif translate_mode:
        message = await update.message.reply_text(get_text("translating_document", language))
    else:
        message = await update.message.reply_text(get_text("analyzing_file", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj plik - w trybie tłumaczenia lub analizy w zależności od opcji
    if translate_mode:
        analysis = await analyze_document(file_bytes, file_name, mode="translate")
        header = f"*{get_text('translated_text', language)}:*\n\n"
    else:
        analysis = await analyze_document(file_bytes, file_name)
        header = f"*{get_text('file_analysis', language)}:* {file_name}\n\n"
    
    # Odejmij kredyty
    description = "Tłumaczenie dokumentu" if translate_mode else "Analiza dokumentu"
    deduct_user_credits(user_id, credit_cost, f"{description}: {file_name}")
    
    # Wyślij analizę do użytkownika
    await message.edit_text(
        f"{header}{analysis}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Dodaj klawiaturę z dodatkowymi opcjami dla plików PDF
    if is_pdf and not translate_mode:
        keyboard = [[
            InlineKeyboardButton(get_text("pdf_translate_button", language), callback_data=f"translate_pdf_{document.file_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            print(f"Błąd dodawania klawiatury: {e}")
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        await update.message.reply_text(
            f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa przesłanych zdjęć"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    credit_cost = CREDIT_COSTS["photo"]
    if not check_user_credits(user_id, credit_cost):
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    # Sprawdź, czy zdjęcie zostało przesłane z komendą tłumaczenia
    caption = update.message.caption or ""
    translate_mode = False
    
    if caption.lower().startswith("/translate") or caption.lower().startswith("przetłumacz"):
        translate_mode = True
    
    # Wybierz zdjęcie o najwyższej rozdzielczości
    photo = update.message.photo[-1]
    
    # Pobierz zdjęcie
    if translate_mode:
        message = await update.message.reply_text("Tłumaczę tekst ze zdjęcia, proszę czekać...")
    else:
        message = await update.message.reply_text(get_text("analyzing_photo", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj zdjęcie w odpowiednim trybie
    if translate_mode:
        result = await analyze_image(file_bytes, f"photo_{photo.file_unique_id}.jpg", mode="translate")
        header = "*Tłumaczenie tekstu ze zdjęcia:*\n\n"
    else:
        result = await analyze_image(file_bytes, f"photo_{photo.file_unique_id}.jpg", mode="analyze")
        header = "*Analiza zdjęcia:*\n\n"
    
    # Odejmij kredyty
    description = "Tłumaczenie tekstu ze zdjęcia" if translate_mode else "Analiza zdjęcia"
    deduct_user_credits(user_id, credit_cost, description)
    
    # Wyślij analizę/tłumaczenie do użytkownika
    await message.edit_text(
        f"{header}{result}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Dodaj klawiaturę z dodatkowymi opcjami
    if not translate_mode:
        keyboard = [[
            InlineKeyboardButton("🔄 Przetłumacz tekst z tego zdjęcia", callback_data=f"translate_photo_{photo.file_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            print(f"Błąd dodawania klawiatury: {e}")
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        await update.message.reply_text(
            f"*Uwaga:* Pozostało Ci tylko *{credits}* kredytów. "
            f"Kup więcej za pomocą komendy /buy.",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_photo_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa przesłanych zdjęć z poleceniem tłumaczenia tekstu"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    credit_cost = CREDIT_COSTS["photo"]
    if not check_user_credits(user_id, credit_cost):
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    # Wybierz zdjęcie o najwyższej rozdzielczości
    photo = update.message.photo[-1]
    
    # Pobierz zdjęcie
    message = await update.message.reply_text("Tłumaczę tekst ze zdjęcia, proszę czekać...")
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj zdjęcie w trybie tłumaczenia
    translation = await analyze_image(file_bytes, f"photo_{photo.file_unique_id}.jpg", mode="translate")
    
    # Odejmij kredyty
    deduct_user_credits(user_id, credit_cost, "Tłumaczenie tekstu ze zdjęcia")
    
    # Wyślij tłumaczenie do użytkownika
    await message.edit_text(
        f"*Tłumaczenie tekstu ze zdjęcia:*\n\n{translation}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        await update.message.reply_text(
            f"*Uwaga:* Pozostało Ci tylko *{credits}* kredytów. "
            f"Kup więcej za pomocą komendy /buy.",
            parse_mode=ParseMode.MARKDOWN
        )
        
async def show_translation_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Wyświetla instrukcje dotyczące tłumaczenia tekstu ze zdjęć
    """
    await update.message.reply_text(
        "📸 *Tłumaczenie tekstu ze zdjęć*\n\n"
        "Masz kilka sposobów, aby przetłumaczyć tekst ze zdjęcia:\n\n"
        "1️⃣ Wyślij zdjęcie, a następnie kliknij przycisk \"🔄 Przetłumacz tekst z tego zdjęcia\" pod analizą\n\n"
        "2️⃣ Wyślij zdjęcie z podpisem \"/translate\" lub \"przetłumacz\"\n\n"
        "3️⃣ Użyj komendy /translate a następnie wyślij zdjęcie\n\n"
        "Bot rozpozna tekst na zdjęciu i przetłumaczy go na język polski. "
        "Ta funkcja jest przydatna do tłumaczenia napisów, dokumentów, menu, znaków itp.",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa zapytań zwrotnych (z przycisków)"""
    query = update.callback_query
    
    # Dodaj debugowanie
    print(f"Otrzymano callback: {query.data}")
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Najpierw odpowiedz, aby usunąć oczekiwanie
    await query.answer()
    
    # Obsługa callbacków płatności
    try:
        if query.data == "menu_section_credits" or query.data == "menu_back_main":
            from handlers.menu_handler import handle_menu_callback
            menu_handled = await handle_menu_callback(update, context)
            if menu_handled:
                return
        
        payment_handled = await handle_payment_callback(update, context)
        if payment_handled:
            return
    except Exception as e:
        print(f"Błąd w obsłudze callbacków płatności: {e}")
        import traceback
        traceback.print_exc()

    # Obsługa callbacków kredytów
    try:
        # Bezpośrednia obsługa callbacków kredytowych
        if query.data == "menu_credits_check" or query.data == "credits_check":
            from handlers.credit_handler import credits_command
            # Utwórz sztuczny obiekt update, aby przekazać do funkcji credits_command
            fake_update = type('obj', (object,), {'effective_user': query.from_user, 'message': query.message})
            await credits_command(fake_update, context)
            return
        elif query.data == "menu_credits_buy" or query.data == "credits_buy":
            from handlers.payment_handler import payment_command
            # Utwórz sztuczny obiekt update, aby przekazać do funkcji payment_command
            fake_update = type('obj', (object,), {'effective_user': query.from_user, 'message': query.message})
            await payment_command(fake_update, context)
            return
        
        # Standardowa obsługa innych callbacków kredytowych
        credit_handled = await handle_credit_callback(update, context)
        if credit_handled:
            return
    except Exception as e:
        print(f"Błąd w obsłudze callbacków kredytów: {e}")
        import traceback
        traceback.print_exc()
    
    # Obsługa przycisków onboardingu
    if query.data.startswith("onboarding_"):
        await handle_onboarding_callback(update, context)
        return
    
    # Najpierw sprawdzamy, czy to callback związany z menu
    if query.data.startswith("menu_"):
        print(f"Rozpoznano callback menu: {query.data}")
        try:
            # Importuj funkcję obsługi menu
            from handlers.menu_handler import handle_menu_callback
            result = await handle_menu_callback(update, context)
            print(f"Wynik obsługi menu: {result}")
            if result:
                return
            # Jeśli menu_handler nie obsłużył callbacku, kontynuujemy poniżej
        except Exception as e:
            print(f"Błąd w obsłudze menu: {str(e)}")
            import traceback
            traceback.print_exc()
            # Wyślij informację o błędzie
            try:
                # Sprawdź, czy wiadomość ma podpis (jest to zdjęcie lub inny typ mediów)
                if hasattr(query.message, 'caption'):
                    await query.edit_message_caption(
                        caption=f"Wystąpił błąd podczas obsługi menu: {str(e)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.edit_message_text(
                        text=f"Wystąpił błąd podczas obsługi menu: {str(e)}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            except:
                pass
    
    # Obsługa wyboru języka
    if query.data.startswith("start_lang_"):
        from handlers.start_handler import handle_language_selection
        await handle_language_selection(update, context)
        return
    
    # Obsługa wyboru języka
    if query.data.startswith("start_lang_"):
        try:
            language_code = query.data[11:]  # Usuń prefiks "start_lang_"
            user_id = query.from_user.id
            
            # Zapisz język w bazie danych
            try:
                from database.supabase_client import update_user_language
                update_user_language(user_id, language_code)
            except Exception as e:
                print(f"Błąd zapisywania języka: {e}")
            
            # Zapisz język w kontekście
            if 'user_data' not in context.chat_data:
                context.chat_data['user_data'] = {}
            
            if user_id not in context.chat_data['user_data']:
                context.chat_data['user_data'][user_id] = {}
            
            context.chat_data['user_data'][user_id]['language'] = language_code
            
            # Pobierz nazwę wybranego języka
            language_name = AVAILABLE_LANGUAGES.get(language_code, language_code)
            
            # Pasek nawigacyjny
            nav_path = get_text("main_menu", language_code, default="Menu główne") + " > " + get_text("menu_settings", language_code) + " > " + get_text("settings_language", language_code)
            
            # Przygotuj wiadomość potwierdzającą
            message = f"*{nav_path}*\n\n" + get_text("language_changed", language_code, language=language_name, default=f"Język został zmieniony na: {language_name}")
            
            # Przyciski powrotu i szybkie akcje
            keyboard = [
                # Pasek szybkiego dostępu
                [
                    InlineKeyboardButton("🆕 " + get_text("new_chat", language_code, default="Nowa rozmowa"), callback_data="quick_new_chat"),
                    InlineKeyboardButton("💬 " + get_text("last_chat", language_code, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
                    InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language_code, default="Kup kredyty"), callback_data="quick_buy_credits")
                ],
                [InlineKeyboardButton("⬅️ " + get_text("back", language_code), callback_data="menu_section_settings")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Aktualizuj wiadomość
            try:
                await update_message(
                    query,
                    message,
                    reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Błąd przy aktualizacji wiadomości wyboru języka: {e}")
                # Spróbuj bez formatowania
                try:
                    if hasattr(query.message, 'caption'):
                        await query.edit_message_caption(
                            caption=message.replace("*", ""),
                            reply_markup=reply_markup
                        )
                    else:
                        await query.edit_message_text(
                            text=message.replace("*", ""),
                            reply_markup=reply_markup
                        )
                except Exception as e2:
                    print(f"Drugi błąd aktualizacji wiadomości: {e2}")
            
            return True
        except Exception as e:
            print(f"Błąd przy obsłudze wyboru języka: {e}")
            import traceback
            traceback.print_exc()
            
            # Powiadom użytkownika o błędzie
            await query.answer("Wystąpił błąd podczas zmiany języka.")
            return True

    # Obsługa wyboru trybu czatu
    if query.data.startswith("mode_"):
        try:
            # Pobierz ID trybu
            mode_id = query.data[5:]  # Usuń prefiks 'mode_'
            
            # Importuj moduł obsługi trybów
            from handlers.mode_handler import handle_mode_selection
            
            # Wywołaj funkcję obsługi
            await handle_mode_selection(update, context, mode_id)
            return True
        except Exception as e:
            print(f"Błąd przy obsłudze wyboru trybu: {e}")
            import traceback
            traceback.print_exc()
            
            # Powiadom użytkownika o błędzie
            await query.answer("Wystąpił błąd podczas wyboru trybu czatu.")
            return True
        
    # Obsługa opcji ustawień
    if query.data.startswith("settings_"):
        try:
            user_id = query.from_user.id
            language = get_user_language(context, user_id)
            
            # Określ typ ustawień
            settings_type = query.data[9:]  # Usuń prefiks 'settings_'
            
            print(f"Obsługa ustawień typu: {settings_type}")
            
            if settings_type == "model":
                # Import funkcji obsługi modelu
                from handlers.menu_handler import handle_model_selection
                await handle_model_selection(update, context)
                return True
            elif settings_type == "language":
                # Import funkcji obsługi języka
                from handlers.menu_handler import handle_language_selection
                await handle_language_selection(update, context)
                return True
            elif settings_type == "name":
                # Import funkcji obsługi nazwy
                from handlers.menu_handler import handle_name_settings
                await handle_name_settings(update, context)
                return True
            else:
                print(f"Nieznany typ ustawień: {settings_type}")
                await query.answer(f"Nieznana opcja ustawień.")
                return True
        except Exception as e:
            print(f"Błąd przy obsłudze ustawień: {e}")
            import traceback
            traceback.print_exc()
            
            # Powiadom użytkownika o błędzie
            await query.answer("Wystąpił błąd podczas zmiany ustawień.")
            return True

    # POPRAWKA: Bezpośrednia obsługa history_view
    if query.data == "history_view":
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Dodaj log
        print(f"Obsługa history_view dla użytkownika {user_id}")
        
        try:
            # Pobierz aktywną konwersację
            from database.supabase_client import get_active_conversation, get_conversation_history
            conversation = get_active_conversation(user_id)
            
            if not conversation:
                # Informacja przez notyfikację
                await query.answer(get_text("history_no_conversation", language))
                
                # Wyświetl komunikat również w wiadomości
                message_text = get_text("history_no_conversation", language)
                keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_section_history")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                result = await update_message(
                    query,
                    message_text,
                    reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                print(f"Wynik update_message dla braku konwersacji: {result}")
                return True
            
            # Pobierz historię konwersacji - tylko gdy konwersacja istnieje
            history = get_conversation_history(conversation['id'])
            
            if not history:
                # Informacja przez notyfikację
                await query.answer(get_text("history_empty", language))
                
                # Wyświetl komunikat również w wiadomości
                message_text = get_text("history_empty", language)
                keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_section_history")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                result = await update_message(
                    query,
                    message_text,
                    reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                print(f"Wynik update_message dla pustej historii: {result}")
                return True
            
            # Przygotuj tekst z historią
            message_text = f"*{get_text('history_title', language)}*\n\n"
            
            for i, msg in enumerate(history[-10:]):  # Ostatnie 10 wiadomości
                sender = get_text("history_user", language) if msg['is_from_user'] else get_text("history_bot", language)
                
                # Skróć treść wiadomości, jeśli jest zbyt długa
                content = msg.get('content', '')
                if len(content) > 100:
                    content = content[:97] + "..."
                    
                # Unikaj formatowania Markdown w treści wiadomości, które mogłoby powodować problemy
                content = content.replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")
                
                message_text += f"{i+1}. **{sender}**: {content}\n\n"
            
            # Dodaj przycisk do powrotu
            keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_section_history")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Spróbuj wysłać z formatowaniem, a jeśli się nie powiedzie, wyślij bez
            try:
                result = await update_message(
                    query,
                    message_text,
                    reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                print(f"Wynik update_message z historią: {result}")
            except Exception as e:
                print(f"Błąd formatowania historii: {e}")
                # Spróbuj bez formatowania
                plain_message = message_text.replace("*", "").replace("**", "")
                result = await update_message(
                    query,
                    plain_message,
                    reply_markup
                )
                print(f"Wynik update_message bez formatowania: {result}")
            
            return True
        except Exception as e:
            print(f"Błąd w obsłudze history_view: {e}")
            import traceback
            traceback.print_exc()
            
            await query.answer("Wystąpił błąd podczas ładowania historii.")
            return True
    
    # POPRAWKA: Bezpośrednia obsługa menu_credits_check
    if query.data == "menu_credits_check" or query.data == "credits_check":
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Pobierz stan kredytów
        from database.credits_client import get_user_credits
        credits = get_user_credits(user_id)
        
        # Klawiatura z opcjami kredytów
        keyboard = [
            [InlineKeyboardButton(get_text("buy_credits_btn", language), callback_data="credits_buy")],
            [InlineKeyboardButton(get_text("credit_stats", language, default="Statystyki"), callback_data="credits_stats")],
            [InlineKeyboardButton(get_text("back", language), callback_data="menu_section_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Tekst informacyjny o kredytach
        message = get_text("credits_info", language, bot_name=BOT_NAME, credits=credits)
        
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                text=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        return
    
    # POPRAWKA: Bezpośrednia obsługa menu_credits_buy
    if query.data == "menu_credits_buy" or query.data == "credits_buy":
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Pobierz pakiety kredytów
        from database.credits_client import get_credit_packages
        packages = get_credit_packages()
        
        packages_text = ""
        for pkg in packages:
            packages_text += f"*{pkg['id']}.* {pkg['name']} - *{pkg['credits']}* {get_text('credits', language)} - *{pkg['price']} PLN*\n"
        
        # Utwórz klawiaturę z pakietami
        keyboard = []
        for pkg in packages:
            keyboard.append([
                InlineKeyboardButton(
                    f"{pkg['name']} - {pkg['credits']} {get_text('credits', language)} ({pkg['price']} PLN)", 
                    callback_data=f"buy_package_{pkg['id']}"
                )
            ])
        
        # Dodaj przycisk dla gwiazdek Telegram
        keyboard.append([
            InlineKeyboardButton("⭐ " + get_text("buy_with_stars", language, default="Kup za gwiazdki Telegram"), 
                                callback_data="show_stars_options")
        ])
        
        # Dodaj przycisk powrotu
        keyboard.append([
            InlineKeyboardButton(get_text("back", language), callback_data="menu_section_credits")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Tekst informacyjny o zakupie kredytów
        message = get_text("buy_credits", language, packages=packages_text)
        
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                text=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        return
    
    # Obsługa przycisku tłumaczenia zdjęcia
    if query.data.startswith("translate_photo_"):
        photo_file_id = query.data.replace("translate_photo_", "")
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
        credit_cost = CREDIT_COSTS["photo"]
        if not check_user_credits(user_id, credit_cost):
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("subscription_expired", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("subscription_expired", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # Pobierz zdjęcie
        try:
            if hasattr(query.message, 'caption'):
                message = await query.edit_message_caption(
                    caption="Tłumaczę tekst ze zdjęcia, proszę czekać...",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                message = await query.edit_message_text(
                    text="Tłumaczę tekst ze zdjęcia, proszę czekać...",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            file = await context.bot.get_file(photo_file_id)
            file_bytes = await file.download_as_bytearray()
            
            # Tłumacz tekst ze zdjęcia
            translation = await analyze_image(file_bytes, f"photo_{photo_file_id}.jpg", mode="translate")
            
            # Odejmij kredyty
            deduct_user_credits(user_id, credit_cost, "Tłumaczenie tekstu ze zdjęcia")
            
            # Wyślij tłumaczenie
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=f"*Tłumaczenie tekstu ze zdjęcia:*\n\n{translation}",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=f"*Tłumaczenie tekstu ze zdjęcia:*\n\n{translation}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Sprawdź aktualny stan kredytów
            credits = get_user_credits(user_id)
            if credits < 5:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            return
        except Exception as e:
            print(f"Błąd przy tłumaczeniu zdjęcia: {e}")
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=f"Wystąpił błąd podczas tłumaczenia zdjęcia: {str(e)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=f"Wystąpił błąd podczas tłumaczenia zdjęcia: {str(e)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
    
    # Obsługa przycisku tłumaczenia PDF
    if query.data.startswith("translate_pdf_"):
        document_file_id = query.data.replace("translate_pdf_", "")
        user_id = query.from_user.id
        language = get_user_language(context, user_id)
        
        # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
        credit_cost = 8  # Koszt tłumaczenia PDF
        if not check_user_credits(user_id, credit_cost):
            await query.answer(get_text("subscription_expired_short", language, default="Niewystarczająca liczba kredytów."))
            
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("subscription_expired", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("subscription_expired", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # Pobierz plik
        try:
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("translating_pdf", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("translating_pdf", language),
                    parse_mode=ParseMode.MARKDOWN
                )
            
            file = await context.bot.get_file(document_file_id)
            file_bytes = await file.download_as_bytearray()
            
            # Tłumacz pierwszy akapit z PDF
            from utils.pdf_translator import translate_pdf_first_paragraph
            result = await translate_pdf_first_paragraph(file_bytes)
            
            # Odejmij kredyty
            deduct_user_credits(user_id, credit_cost, "Tłumaczenie pierwszego akapitu z PDF")
            
            # Przygotuj odpowiedź
            if result["success"]:
                response = f"*{get_text('pdf_translation_result', language)}*\n\n"
                response += f"*{get_text('original_text', language)}:*\n{result['original_text'][:500]}...\n\n"
                response += f"*{get_text('translated_text', language)}:*\n{result['translated_text'][:500]}..."
            else:
                response = f"*{get_text('pdf_translation_error', language)}*\n\n{result['error']}"
            
            # Wyślij wynik tłumaczenia
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=response,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=response,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Sprawdź aktualny stan kredytów
            credits = get_user_credits(user_id)
            if credits < 5:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            return
        except Exception as e:
            print(f"Błąd przy tłumaczeniu PDF: {e}")
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=f"{get_text('pdf_translation_error', language)}: {str(e)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=f"{get_text('pdf_translation_error', language)}: {str(e)}",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
    
    # Obsługa historii
    if query.data.startswith("history_"):
        if query.data == "history_new":
            # Twórz nową konwersację
            conversation = create_new_conversation(user_id)
            # Sprawdź, czy wiadomość ma podpis (jest to zdjęcie lub inny typ mediów)
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("new_chat_success", get_user_language(context, user_id)),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("new_chat_success", get_user_language(context, user_id)),
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        elif query.data == "history_export":
            # Eksportuj bieżącą konwersację
            from handlers.export_handler import export_conversation
            # Tworzymy sztuczny obiekt update do przekazania do funkcji export_conversation
            class FakeUpdate:
                class FakeMessage:
                    def __init__(self, chat_id, message_id):
                        self.chat_id = chat_id
                        self.message_id = message_id
                        self.chat = type('obj', (object,), {'send_action': lambda *args, **kwargs: None})
                    async def reply_text(self, *args, **kwargs):
                        pass
                    async def reply_document(self, *args, **kwargs):
                        pass
                def __init__(self, query):
                    self.message = self.FakeMessage(query.message.chat_id, query.message.message_id)
                    self.effective_user = query.from_user
                    self.effective_chat = type('obj', (object,), {'id': query.message.chat_id})
            
            fake_update = FakeUpdate(query)
            await export_conversation(fake_update, context)
            # Informacja o eksporcie
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption="Eksportowanie konwersacji do PDF...",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text="Eksportowanie konwersacji do PDF...",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        elif query.data == "history_delete":
            # Pytanie o potwierdzenie usunięcia historii
            keyboard = [
                [
                    InlineKeyboardButton(get_text("yes", get_user_language(context, user_id)), callback_data="history_confirm_delete"),
                    InlineKeyboardButton(get_text("no", get_user_language(context, user_id)), callback_data="menu_section_history")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("history_delete_confirm", get_user_language(context, user_id)),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("history_delete_confirm", get_user_language(context, user_id)),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            return
    
    # Obsługa przycisku restartu bota
    if query.data == "restart_bot":
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        language = get_user_language(context, user_id)
        
        restart_message = get_text("restarting_bot", language)
        try:
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(caption=restart_message)
            else:
                await query.edit_message_text(text=restart_message)
        except Exception as e:
            print(f"Błąd przy aktualizacji wiadomości: {e}")
        
        # Resetowanie konwersacji - tworzymy nową konwersację i czyścimy kontekst
        conversation = create_new_conversation(user_id)
        
        # Zachowujemy wybrane ustawienia użytkownika (język, model)
        user_data = {}
        if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
            # Pobieramy tylko podstawowe ustawienia, reszta jest resetowana
            old_user_data = context.chat_data['user_data'][user_id]
            if 'language' in old_user_data:
                user_data['language'] = old_user_data['language']
            if 'current_model' in old_user_data:
                user_data['current_model'] = old_user_data['current_model']
            if 'current_mode' in old_user_data:
                user_data['current_mode'] = old_user_data['current_mode']
        
        # Resetujemy dane użytkownika w kontekście i ustawiamy tylko zachowane ustawienia
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        context.chat_data['user_data'][user_id] = user_data
        
        # Potwierdź restart
        restart_complete = get_text("restart_command", language)
        
        # Utwórz klawiaturę menu
        keyboard = [
            [
                InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes"),
                InlineKeyboardButton(get_text("image_generate", language), callback_data="menu_image_generate")
            ],
            [
                InlineKeyboardButton(get_text("menu_credits", language), callback_data="menu_section_credits"),
                InlineKeyboardButton(get_text("menu_dialog_history", language), callback_data="menu_section_history")
            ],
            [
                InlineKeyboardButton(get_text("menu_settings", language), callback_data="menu_section_settings"),
                InlineKeyboardButton(get_text("menu_help", language), callback_data="menu_help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Wyślij nową wiadomość z menu
        try:
            # Używamy welcome_message zamiast main_menu + status
            welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=restart_complete + "\n\n" + welcome_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Zapisz ID wiadomości menu i stan menu
            from handlers.menu_handler import store_menu_state
            store_menu_state(context, user_id, 'main', message.message_id)
        except Exception as e:
            print(f"Błąd przy wysyłaniu wiadomości po restarcie: {e}")
            # Próbuj wysłać prostą wiadomość
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=restart_complete
                )
            except Exception as e2:
                print(f"Nie udało się wysłać nawet prostej wiadomości: {e2}")
        
        return
        
    # Obsługa historii rozmów
    if query.data == "history_confirm_delete":
        user_id = query.from_user.id
        # Twórz nową konwersację (efektywnie "usuwając" historię)
        conversation = create_new_conversation(user_id)
        
        if conversation:
            from handlers.menu_handler import update_menu
            await update_menu(update, context, 'history')
        else:
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption="Wystąpił błąd podczas czyszczenia historii.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text="Wystąpił błąd podczas czyszczenia historii.",
                    parse_mode=ParseMode.MARKDOWN
                )
        return
    
    # Specjalna obsługa przycisku powrotu do głównego menu
    if query.data == "menu_back_main":
        keyboard = [
            [
                InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes"),
                InlineKeyboardButton(get_text("image_generate", language), callback_data="menu_image_generate")
            ],
            [
                InlineKeyboardButton(get_text("menu_credits", language), callback_data="menu_section_credits"),
                InlineKeyboardButton(get_text("menu_dialog_history", language), callback_data="menu_section_history")
            ],
            [
                InlineKeyboardButton(get_text("menu_settings", language), callback_data="menu_section_settings"),
                InlineKeyboardButton(get_text("menu_help", language), callback_data="menu_help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Używanie welcome_message
        welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
        
        try:
            # Wyślij nową wiadomość zamiast edytować starą
            message = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=welcome_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            # Zapisz ID nowej wiadomości menu
            store_menu_state(context, user_id, 'main', message.message_id)
            
            # Opcjonalnie usuń starą wiadomość
            try:
                await query.message.delete()
            except:
                pass
                
            return
        except Exception as e:
            print(f"Błąd przy obsłudze menu_back_main: {e}")
            # W przypadku błędu, kontynuujemy do standardowej obsługi

    elif query.data == "quick_new_chat":
        try:
            user_id = query.from_user.id
            language = get_user_language(context, user_id)
            
            # Utwórz nową konwersację
            from database.supabase_client import create_new_conversation
            conversation = create_new_conversation(user_id)
            
            await query.answer(get_text("new_chat_created", language, default="Utworzono nową rozmowę"))
            
            # Zamknij menu, aby użytkownik mógł zacząć pisać
            await query.message.delete()
            
            # Ewentualnie wyślij komunikat potwierdzający utworzenie nowej rozmowy
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=get_text("new_chat_created_message", language, default="✅ Utworzono nową rozmowę. Możesz zacząć pisać!")
            )
            return True
        except Exception as e:
            print(f"Błąd przy tworzeniu nowej rozmowy: {e}")
            await handle_callback_error(
                query,
                "Wystąpił błąd podczas tworzenia nowej rozmowy.",
                full_error=str(e)
            )
            return True

    elif query.data == "quick_last_chat":
        try:
            user_id = query.from_user.id
            language = get_user_language(context, user_id)
            
            # Pobierz aktywną konwersację
            from database.supabase_client import get_active_conversation
            conversation = get_active_conversation(user_id)
            
            if conversation:
                await query.answer(get_text("returning_to_last_chat", language, default="Powrót do ostatniej rozmowy"))
                
                # Zamknij menu i pozwól użytkownikowi wrócić do czatu
                await query.message.delete()
            else:
                await query.answer(get_text("no_active_chat", language, default="Brak aktywnej rozmowy"))
                
                # Utwórz nową konwersację i wróć do głównego menu
                from database.supabase_client import create_new_conversation
                create_new_conversation(user_id)
                
                # Zamknij menu, aby użytkownik mógł zacząć pisać
                await query.message.delete()
                
                # Ewentualnie wyślij komunikat
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=get_text("new_chat_created_message", language, default="✅ Utworzono nową rozmowę. Możesz zacząć pisać!")
                )
            
            return True
        except Exception as e:
            print(f"Błąd przy obsłudze ostatniej rozmowy: {e}")
            await handle_callback_error(
                query,
                "Wystąpił błąd podczas powrotu do ostatniej rozmowy.",
                full_error=str(e)
            )
            return True

    elif query.data == "quick_buy_credits" or query.data == "menu_credits_buy":
        try:
            user_id = query.from_user.id
            language = get_user_language(context, user_id)
            
            # Pobierz dostępne metody płatności
            from database.payment_client import get_available_payment_methods
            payment_methods = get_available_payment_methods(language)
            
            if not payment_methods:
                await query.answer(get_text("payment_methods_unavailable", language, 
                                default="Obecnie brak dostępnych metod płatności. Spróbuj ponownie później."))
                return True
            
            # Utwórz przyciski dla każdej metody płatności
            keyboard = []
            for method in payment_methods:
                keyboard.append([
                    InlineKeyboardButton(
                        method["name"], 
                        callback_data=f"payment_method_{method['code']}"
                    )
                ])
            
            # Dodaj przycisk powrotu
            keyboard.append([
                InlineKeyboardButton(
                    get_text("back", language), 
                    callback_data="menu_section_credits"
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Wyświetl menu metod płatności
            if hasattr(query.message, 'caption'):
                await query.edit_message_caption(
                    caption=get_text("select_payment_method", language, default="Wybierz metodę płatności:"),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    text=get_text("select_payment_method", language, default="Wybierz metodę płatności:"),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            return True
        except Exception as e:
            print(f"Błąd przy wyświetlaniu metod płatności: {e}")
            import traceback
            traceback.print_exc()
            
            await handle_callback_error(
                query,
                "Wystąpił błąd podczas ładowania metod płatności.",
                full_error=str(e)
            )
            return True

    # Jeśli dotarliśmy tutaj, oznacza to, że callback nie został obsłużony
    print(f"Nieobsłużony callback: {query.data}")
    try:
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=f"Nieznany przycisk. Spróbuj ponownie później.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                text=f"Nieznany przycisk. Spróbuj ponownie później.",
                parse_mode=ParseMode.MARKDOWN
            )
    except:
        pass

# Rejestracja handlerów
# Rejestracja handlerów
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("status", check_status))
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CommandHandler("mode", show_modes))
application.add_handler(CommandHandler("models", lambda u, c: show_modes(u, c)))
application.add_handler(CommandHandler("newchat", new_chat))
application.add_handler(CommandHandler("image", generate_image))
application.add_handler(CommandHandler("export", export_conversation))
application.add_handler(CommandHandler("restart", restart_command))
application.add_handler(CommandHandler("code", code_command))
application.add_handler(CommandHandler("creditstats", credit_analytics_command))
application.add_handler(CommandHandler("translate", translate_command))
application.add_handler(CommandHandler("language", language_command))
application.add_handler(CommandHandler("onboarding", onboarding_command))
application.add_handler(CommandHandler("setname", set_user_name))
application.add_handler(CommandHandler("payment", payment_command))
application.add_handler(CommandHandler("subscription", subscription_command))
application.add_handler(CommandHandler("transactions", transactions_command))

# Admin commands
application.add_handler(CommandHandler("gencode", admin_generate_code))
application.add_handler(CommandHandler("addpackage", add_package))
application.add_handler(CommandHandler("listpackages", list_packages))
application.add_handler(CommandHandler("togglepackage", toggle_package))
application.add_handler(CommandHandler("adddefaultpackages", add_default_packages))

# Handlery dla wiadomości
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# Handlery dla callbacków inline
application.add_handler(CallbackQueryHandler(handle_callback_query))

# Rozpoczęcie nasłuchiwania
if __name__ == "__main__":
    print("Uruchamiam bota...")
    try:
        print("Rozpoczynam nasłuchiwanie wiadomości...")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Błąd podczas uruchamiania bota: {e}")
        import traceback
        traceback.print_exc()