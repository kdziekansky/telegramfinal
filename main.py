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
from utils.ui_elements import credit_status_bar, info_card, section_divider, progress_bar
from utils.message_formatter_enhanced import (
    format_long_message, format_credit_info, enhance_credits_display, 
    format_mode_selection, enhance_help_message
)
from utils.visual_styles import style_message, create_header, create_section, create_status_indicator
from utils.tips import get_random_tip, should_show_tip, get_contextual_tip
from utils.credit_warnings import (
    check_operation_cost, get_low_credits_notification, format_credit_usage_report,
    get_credit_recommendation
)
from telegram.ext import Application
from config import TELEGRAM_TOKEN
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ReplyKeyboardRemove
from handlers.help_handler import help_command
from utils.error_handler import handle_callback_error
from utils.menu_utils import update_menu
from utils.user_utils import get_user_language
from handlers.translate_handler import translate_command
from utils.menu_utils import update_menu
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
    handle_menu_callback, set_user_name, get_user_language, store_menu_state,
    handle_settings_callbacks  # usunięto handle_mode_selection
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
    
    # Oznacz czat jako zainicjowany
    from utils.user_utils import mark_chat_initialized
    mark_chat_initialized(context, user_id)
    
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
    """Obsługa wiadomości tekstowych od użytkownika ze strumieniowaniem odpowiedzi i ulepszonym formatowaniem"""
    user_id = update.effective_user.id
    user_message = update.message.text
    language = get_user_language(context, user_id)
    
    print(f"Otrzymano wiadomość od użytkownika {user_id}: {user_message}")
    
    # Sprawdź, czy użytkownik zainicjował czat
    from utils.user_utils import is_chat_initialized
    if not is_chat_initialized(context, user_id):
        # Enhanced UI for chat initialization prompt
        message = create_header("Rozpocznij nowy czat", "chat")
        message += (
            "Aby rozpocząć używanie AI, najpierw utwórz nowy czat używając /newchat "
            "lub przycisku poniżej. Możesz również wybrać tryb czatu z menu."
        )
        
        keyboard = [
            [InlineKeyboardButton("🆕 " + get_text("start_new_chat", language, default="Rozpocznij nowy czat"), callback_data="quick_new_chat")],
            [InlineKeyboardButton("📋 " + get_text("select_mode", language, default="Wybierz tryb czatu"), callback_data="menu_section_chat_modes")],
            [InlineKeyboardButton("❓ " + get_text("menu_help", language, default="Pomoc"), callback_data="menu_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return
    
    # Określ tryb i koszt kredytów
    current_mode = "no_mode"
    credit_cost = 1
    
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_mode' in user_data and user_data['current_mode'] in CHAT_MODES:
            current_mode = user_data['current_mode']
            credit_cost = CHAT_MODES[current_mode]["credit_cost"]
    
    print(f"Tryb: {current_mode}, koszt kredytów: {credit_cost}")
    
    # Get current credits
    credits = get_user_credits(user_id)
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    if not check_user_credits(user_id, credit_cost):
        # Enhanced credit warning with visual indicators
        warning_message = create_header("Niewystarczające kredyty", "warning")
        warning_message += (
            f"Nie masz wystarczającej liczby kredytów, aby wysłać wiadomość.\n\n"
            f"▪️ Koszt operacji: *{credit_cost}* kredytów\n"
            f"▪️ Twój stan kredytów: *{credits}* kredytów\n\n"
            f"Potrzebujesz jeszcze *{credit_cost - credits}* kredytów."
        )
        
        # Add credit recommendation if available
        recommendation = get_credit_recommendation(user_id, context)
        if recommendation:
            warning_message += "\n\n" + create_section("Rekomendowany pakiet", 
                f"▪️ {recommendation['package_name']} - {recommendation['credits']} kredytów\n"
                f"▪️ Cena: {recommendation['price']} PLN\n"
                f"▪️ {recommendation['reason']}")
        
        keyboard = [
            [InlineKeyboardButton("💳 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="menu_credits_buy")],
            [InlineKeyboardButton("⬅️ " + get_text("menu_back_main", language, default="Menu główne"), callback_data="menu_back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            warning_message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check operation cost and show warning if needed
    cost_warning = check_operation_cost(user_id, credit_cost, credits, "Wiadomość AI", context)
    if cost_warning['require_confirmation'] and cost_warning['level'] in ['warning', 'critical']:
        # Show warning and ask for confirmation
        warning_message = create_header("Potwierdzenie kosztu", "warning")
        warning_message += cost_warning['message'] + "\n\nCzy chcesz kontynuować?"
        
        # Create confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Tak, wyślij", callback_data=f"confirm_message"),
                InlineKeyboardButton("❌ Anuluj", callback_data="cancel_operation")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store message in context for later use
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        if user_id not in context.chat_data['user_data']:
            context.chat_data['user_data'][user_id] = {}
            
        context.chat_data['user_data'][user_id]['pending_message'] = user_message
        
        await update.message.reply_text(
            warning_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
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
    """Obsługa przesłanych dokumentów z naturalnym interfejsem"""
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
    
    # Pobierz tekst dołączony do dokumentu (jeśli istnieje)
    caption = update.message.caption or ""
    
    # Sprawdź, czy to jest plik PDF
    is_pdf = file_name.lower().endswith('.pdf')
    
    # Określ akcję na podstawie tekstu użytkownika
    if not caption:
        # Jeśli nie ma tekstu, zapytaj co użytkownik chce zrobić i pokaż przykłady
        # Zapisz ID dokumentu w kontekście do późniejszego użycia
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        if user_id not in context.chat_data['user_data']:
            context.chat_data['user_data'][user_id] = {}
            
        context.chat_data['user_data'][user_id]['last_document_id'] = document.file_id
        context.chat_data['user_data'][user_id]['last_document_name'] = file_name
        
        # Tekst z sugestiami w naturalnym języku
        if is_pdf:
            suggestions_text = get_text("pdf_suggestions", language, default=
                "Co chcesz zrobić z tym dokumentem PDF? Odpowiedz jednym z przykładów:\n\n"
                "• \"Analizuj ten dokument\"\n"
                "• \"Przetłumacz ten dokument\"\n"
                "• \"Streszcz zawartość pliku\"\n"
                "• \"Wyciągnij najważniejsze informacje z tego PDF\"\n\n"
                "Po prostu odpowiedz na tę wiadomość z tym, co chcesz zrobić."
            )
        else:
            suggestions_text = get_text("document_suggestions", language, default=
                "Co chcesz zrobić z tym dokumentem? Odpowiedz jednym z przykładów:\n\n"
                "• \"Analizuj ten dokument\"\n"
                "• \"Streszcz zawartość pliku\"\n"
                "• \"Opisz co zawiera ten plik\"\n\n"
                "Po prostu odpowiedz na tę wiadomość z tym, co chcesz zrobić."
            )
        
        await update.message.reply_text(suggestions_text)
        return
    
    # Analizuj intencję użytkownika na podstawie tekstu
    caption_lower = caption.lower()
    
    # Sprawdź, czy użytkownik chce tłumaczenie
    if any(word in caption_lower for word in ["tłumacz", "przetłumacz", "translate", "переводить"]):
        if is_pdf:
            # Wywołaj funkcję do tłumaczenia PDF
            from handlers.pdf_handler import handle_pdf_translation
            await handle_pdf_translation(update, context)
        else:
            # Dla innych dokumentów wykonaj analizę z informacją o braku możliwości tłumaczenia
            message = await update.message.reply_text(get_text("analyzing_file", language))
            await update.message.chat.send_action(action=ChatAction.TYPING)
            
            file = await context.bot.get_file(document.file_id)
            file_bytes = await file.download_as_bytearray()
            
            # Analizuj dokument z dodatkową informacją o braku tłumaczenia
            result = await analyze_document(file_bytes, file_name)
            
            # Odejmij kredyty
            deduct_user_credits(user_id, credit_cost, f"Analiza dokumentu: {file_name}")
            
            # Wyślij analizę
            await message.edit_text(
                f"*{get_text('file_analysis', language)}:* {file_name}\n\n"
                f"{result}\n\n"
                f"_Uwaga: Tłumaczenie jest dostępne tylko dla plików PDF._",
                parse_mode=ParseMode.MARKDOWN
            )
        return
    
    # Domyślnie wykonaj analizę dokumentu
    message = await update.message.reply_text(get_text("analyzing_file", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj dokument
    result = await analyze_document(file_bytes, file_name)
    
    # Odejmij kredyty
    deduct_user_credits(user_id, credit_cost, f"Analiza dokumentu: {file_name}")
    
    # Wyślij analizę do użytkownika
    await message.edit_text(
        f"*{get_text('file_analysis', language)}:* {file_name}\n\n{result}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        await update.message.reply_text(
            f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa przesłanych zdjęć z naturalnym interfejsem jak ChatGPT"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
    credit_cost = CREDIT_COSTS["photo"]
    if not check_user_credits(user_id, credit_cost):
        await update.message.reply_text(get_text("subscription_expired", language))
        return
    
    # Pobierz tekst dołączony do zdjęcia (jeśli istnieje)
    caption = update.message.caption or ""
    
    # Określ akcję na podstawie tekstu użytkownika
    if not caption:
        # Jeśli nie ma tekstu, zapytaj co użytkownik chce zrobić i pokaż przykłady
        # Zapisz ID zdjęcia w kontekście do późniejszego użycia
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        if user_id not in context.chat_data['user_data']:
            context.chat_data['user_data'][user_id] = {}
            
        context.chat_data['user_data'][user_id]['last_photo_id'] = update.message.photo[-1].file_id
        
        # Tekst z sugestiami w naturalnym języku
        suggestions_text = get_text("photo_suggestions", language, default=
            "Co chcesz zrobić z tym zdjęciem? Odpowiedz jednym z przykładów:\n\n"
            "• \"Opisz co widzisz na zdjęciu\"\n"
            "• \"Przetłumacz tekst z tego zdjęcia\"\n"
            "• \"Przetłumacz tekst ze zdjęcia na angielski\"\n"
            "• \"Analizuj obraz i powiedz co przedstawia\"\n"
            "• \"Jaki obiekt jest na tym obrazie?\"\n\n"
            "Po prostu odpowiedz na tę wiadomość z tym, co chcesz zrobić."
        )
        
        await update.message.reply_text(suggestions_text)
        return
        
    # Analizuj intencję użytkownika na podstawie tekstu
    caption_lower = caption.lower()
    
    # Sprawdź, czy użytkownik chce tłumaczenie
    if any(word in caption_lower for word in ["tłumacz", "przetłumacz", "translate", "переводить"]):
        mode = "translate"
        message = await update.message.reply_text(get_text("translating_image", language))
    # Sprawdź, czy użytkownik chce analizę
    elif any(word in caption_lower for word in ["analizuj", "analiza", "opisz", "analyze", "describe", "what is"]):
        mode = "analyze"
        message = await update.message.reply_text(get_text("analyzing_photo", language))
    # Domyślnie wykonaj analizę
    else:
        mode = "analyze"
        message = await update.message.reply_text(get_text("analyzing_photo", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    # Wybierz zdjęcie o najwyższej rozdzielczości
    photo = update.message.photo[-1]
    
    # Pobierz zdjęcie
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj zdjęcie w odpowiednim trybie
    result = await analyze_image(file_bytes, f"photo_{photo.file_unique_id}.jpg", mode=mode)
    
    # Odejmij kredyty
    description = "Tłumaczenie tekstu ze zdjęcia" if mode == "translate" else "Analiza zdjęcia"
    deduct_user_credits(user_id, credit_cost, description)
    
    # Wyślij analizę/tłumaczenie do użytkownika
    header = "*Tłumaczenie tekstu ze zdjęcia:*\n\n" if mode == "translate" else "*Analiza zdjęcia:*\n\n"
    await message.edit_text(
        f"{header}{result}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Sprawdź aktualny stan kredytów
    credits = get_user_credits(user_id)
    if credits < 5:
        await update.message.reply_text(
            f"*{get_text('low_credits_warning', language)}* {get_text('low_credits_message', language, credits=credits)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa zapytań zwrotnych (z przycisków)"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodaj logger
    print(f"Otrzymano callback: {query.data} od użytkownika {user_id}")
    
    # Najpierw odpowiedz, aby usunąć oczekiwanie
    await query.answer()
    
    # Daj priorytet obsłudze wyboru języka w /start
    if query.data.startswith("start_lang_"):
        try:
            from handlers.start_handler import handle_language_selection
            await handle_language_selection(update, context)
            return
        except Exception as e:
            print(f"Błąd w obsłudze wyboru języka: {e}")
            import traceback
            traceback.print_exc()
    
    # 1. Menu główne i nawigacja
    if query.data.startswith("menu_"):
        try:
            from handlers.menu_handler import handle_menu_callback
            handled = await handle_menu_callback(update, context)
            if handled:
                return
        except Exception as e:
            print(f"Błąd w obsłudze menu: {e}")
            import traceback
            traceback.print_exc()
    
    # 2. Tryby czatu - POPRAWIONE
    elif query.data.startswith("mode_"):
        try:
            from handlers.mode_handler import handle_mode_selection
            await handle_mode_selection(update, context)
            return
        except Exception as e:
            print(f"Błąd przy obsłudze wyboru trybu: {e}")
            import traceback
            traceback.print_exc()
            # Spróbuj wyświetlić informację o błędzie
            try:
                keyboard = [[InlineKeyboardButton("⬅️ Menu główne", callback_data="menu_back_main")]]
                await query.edit_message_text(
                    text=f"Wystąpił błąd podczas wyboru trybu: {str(e)[:100]}...\nSpróbuj ponownie później.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                pass
    
    # 3. Ustawienia
    elif query.data.startswith("settings_") or query.data.startswith("model_") or query.data.startswith("start_lang_"):
        try:
            # Używamy funkcji już zaimportowanej na poziomie globalnym
            handled = await handle_settings_callbacks(update, context)
            if handled:
                return
        except Exception as e:
            print(f"Błąd w obsłudze ustawień: {e}")
            import traceback
            traceback.print_exc()
    
    # 4. Kredyty
    elif query.data.startswith("credits_") or query.data == "menu_credits_check" or query.data == "menu_credits_buy":
        try:
            from handlers.menu_handler import handle_credits_callbacks
            handled = await handle_credits_callbacks(update, context)
            if handled:
                return
        except Exception as e:
            print(f"Błąd w obsłudze kredytów: {e}")
            import traceback
            traceback.print_exc()
    
    # 5. Płatności
    elif query.data.startswith("payment_") or query.data.startswith("buy_package_"):
        try:
            from handlers.menu_handler import handle_payment_callbacks
            handled = await handle_payment_callbacks(update, context)
            if handled:
                return
        except Exception as e:
            print(f"Błąd w obsłudze płatności: {e}")
            import traceback
            traceback.print_exc()
    
    # 6. Historia
    elif query.data.startswith("history_"):
        try:
            from handlers.menu_handler import handle_history_callbacks
            handled = await handle_history_callbacks(update, context)
            if handled:
                return
        except Exception as e:
            print(f"Błąd w obsłudze historii: {e}")
            import traceback
            traceback.print_exc()
    
    # 7. Onboarding
    elif query.data.startswith("onboarding_"):
        try:
            await handle_onboarding_callback(update, context)
            return
        except Exception as e:
            print(f"Błąd w obsłudze onboardingu: {e}")
            import traceback
            traceback.print_exc()
    
    # 8. Tematy konwersacji
    elif query.data.startswith("theme_") or query.data == "new_theme" or query.data == "no_theme":
        try:
            from handlers.theme_handler import handle_theme_callback
            await handle_theme_callback(update, context)
            return
        except Exception as e:
            print(f"Błąd w obsłudze tematów: {e}")
            import traceback
            traceback.print_exc()
    
    # 9. Tłumaczenie zdjęć
    elif query.data.startswith("translate_photo_"):
        try:
            photo_file_id = query.data.replace("translate_photo_", "")
            
            # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
            credit_cost = CREDIT_COSTS["photo"]
            if not check_user_credits(user_id, credit_cost):
                await update_menu(
                    query,
                    get_text("subscription_expired", language),
                    InlineKeyboardMarkup([[InlineKeyboardButton(get_text("back", language), callback_data="menu_back_main")]])
                )
                return
            
            # Informuj o rozpoczęciu tłumaczenia
            await update_menu(
                query,
                get_text("translating_image", language),
                None
            )
            
            # Pobierz zdjęcie
            file = await context.bot.get_file(photo_file_id)
            file_bytes = await file.download_as_bytearray()
            
            # Tłumacz tekst ze zdjęcia
            translation = await analyze_image(file_bytes, f"photo_{photo_file_id}.jpg", mode="translate")
            
            # Odejmij kredyty
            deduct_user_credits(user_id, credit_cost, "Tłumaczenie tekstu ze zdjęcia")
            
            # Wyślij tłumaczenie
            await update_menu(
                query,
                f"*{get_text('translation_result', language)}*\n\n{translation}",
                InlineKeyboardMarkup([[InlineKeyboardButton(get_text("back", language), callback_data="menu_back_main")]]),
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            print(f"Błąd przy tłumaczeniu zdjęcia: {e}")
            import traceback
            traceback.print_exc()

    # Obsługa nowych callbacków dla zdjęć
    elif query.data == "analyze_photo" or query.data == "translate_photo":
        # Pobierz ID zdjęcia z kontekstu
        if 'user_data' not in context.chat_data or user_id not in context.chat_data['user_data'] or 'last_photo_id' not in context.chat_data['user_data'][user_id]:
            await query.answer("Nie znaleziono zdjęcia. Wyślij je ponownie.")
            return
            
        photo_id = context.chat_data['user_data'][user_id]['last_photo_id']
        mode = "translate" if query.data == "translate_photo" else "analyze"
        
        # Pobierz koszt
        credit_cost = CREDIT_COSTS["photo"]
        if not check_user_credits(user_id, credit_cost):
            await query.answer(get_text("subscription_expired", language))
            return
        
        # Informuj o rozpoczęciu analizy
        message = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_text("translating_image" if mode == "translate" else "analyzing_photo", language)
        )
        
        try:
            # Pobierz zdjęcie
            file = await context.bot.get_file(photo_id)
            file_bytes = await file.download_as_bytearray()
            
            # Analizuj zdjęcie
            result = await analyze_image(file_bytes, f"photo_{photo_id}.jpg", mode=mode)
            
            # Odejmij kredyty
            description = "Tłumaczenie tekstu ze zdjęcia" if mode == "translate" else "Analiza zdjęcia"
            deduct_user_credits(user_id, credit_cost, description)
            
            # Wyślij wynik
            header = "*Tłumaczenie tekstu ze zdjęcia:*\n\n" if mode == "translate" else "*Analiza zdjęcia:*\n\n"
            await message.edit_text(
                f"{header}{result}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Błąd przy analizie zdjęcia: {e}")
            await message.edit_text("Wystąpił błąd podczas analizy zdjęcia. Spróbuj ponownie.")

    elif query.data.startswith("translate_pdf_"):
        try:
            document_file_id = query.data.replace("translate_pdf_", "")
            
            # Sprawdź, czy użytkownik ma wystarczającą liczbę kredytów
            credit_cost = 8  # Koszt tłumaczenia PDF
            if not check_user_credits(user_id, credit_cost):
                await update_menu(
                    query,
                    get_text("subscription_expired", language),
                    InlineKeyboardMarkup([[InlineKeyboardButton(get_text("back", language), callback_data="menu_back_main")]])
                )
                return
            
            # Informuj o rozpoczęciu tłumaczenia
            await update_menu(
                query,
                get_text("translating_pdf", language),
                None
            )
            
            # Pobierz plik
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
            await update_menu(
                query,
                response,
                InlineKeyboardMarkup([[InlineKeyboardButton(get_text("back", language), callback_data="menu_back_main")]]),
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            print(f"Błąd przy tłumaczeniu PDF: {e}")
            import traceback
            traceback.print_exc()

    # Obsługa nowych callbacków dla dokumentów
    elif query.data == "analyze_document" or query.data == "translate_document":
        # Pobierz ID dokumentu z kontekstu
        if ('user_data' not in context.chat_data or 
            user_id not in context.chat_data['user_data'] or 
            'last_document_id' not in context.chat_data['user_data'][user_id]):
            await query.answer("Nie znaleziono dokumentu. Wyślij go ponownie.")
            return
            
        document_id = context.chat_data['user_data'][user_id]['last_document_id']
        file_name = context.chat_data['user_data'][user_id].get('last_document_name', 'dokument')
        
        # Sprawdź czy to jest prośba o tłumaczenie PDF
        if query.data == "translate_document" and file_name.lower().endswith('.pdf'):
            # Zasymuluj aktualizację z oryginalnym plikiem PDF
            class MockDocument:
                def __init__(self, file_id, file_name):
                    self.file_id = file_id
                    self.file_name = file_name
            
            class MockMessage:
                def __init__(self, chat_id, document):
                    self.chat_id = chat_id
                    self.document = document
                    self.chat = type('obj', (object,), {'id': chat_id, 'send_action': lambda action: None})
                    
                async def reply_text(self, text):
                    return await context.bot.send_message(chat_id=self.chat_id, text=text)
            
            # Utwórz aktualizację z dokumentem
            mock_document = MockDocument(document_id, file_name)
            update.message = MockMessage(query.message.chat_id, mock_document)
            
            # Wywołaj handler PDF
            from handlers.pdf_handler import handle_pdf_translation
            await handle_pdf_translation(update, context)
            return
        
        # Obsługa standardowej analizy dokumentu
        # Pobierz koszt
        credit_cost = CREDIT_COSTS["document"]
        if not check_user_credits(user_id, credit_cost):
            await query.answer(get_text("subscription_expired", language))
            return
        
        # Informuj o rozpoczęciu analizy
        message = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=get_text("analyzing_file", language)
        )
        
        try:
            # Pobierz dokument
            file = await context.bot.get_file(document_id)
            file_bytes = await file.download_as_bytearray()
            
            # Analizuj dokument
            result = await analyze_document(file_bytes, file_name)
            
            # Odejmij kredyty
            deduct_user_credits(user_id, credit_cost, f"Analiza dokumentu: {file_name}")
            
            # Wyślij wynik
            await message.edit_text(
                f"*{get_text('file_analysis', language)}:* {file_name}\n\n{result}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Błąd przy analizie dokumentu: {e}")
            await message.edit_text("Wystąpił błąd podczas analizy dokumentu. Spróbuj ponownie.")

    # 10. Szybkie akcje
    elif query.data == "quick_new_chat":
        try:
            # Utwórz nową konwersację
            from database.supabase_client import create_new_conversation
            from utils.user_utils import mark_chat_initialized
            
            conversation = create_new_conversation(user_id)
            mark_chat_initialized(context, user_id)  # Dodaj tę linię
            
            await query.answer(get_text("new_chat_created", language))
            
            # Zamknij menu, aby użytkownik mógł zacząć pisać
            await query.message.delete()
            
            # Wyślij komunikat potwierdzający
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=get_text("new_chat_created_message", language)
            )
            return
        except Exception as e:
            print(f"Błąd przy tworzeniu nowej rozmowy: {e}")
            import traceback
            traceback.print_exc()

    elif query.data == "quick_last_chat":
        try:
            # Pobierz aktywną konwersację
            from database.supabase_client import get_active_conversation
            conversation = get_active_conversation(user_id)
            
            if conversation:
                await query.answer(get_text("returning_to_last_chat", language))
                
                # Zamknij menu
                await query.message.delete()
            else:
                await query.answer(get_text("no_active_chat", language))
                
                # Utwórz nową konwersację
                from database.supabase_client import create_new_conversation
                create_new_conversation(user_id)
                
                # Zamknij menu
                await query.message.delete()
                
                # Wyślij komunikat
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=get_text("new_chat_created_message", language)
                )
            return
        except Exception as e:
            print(f"Błąd przy obsłudze ostatniej rozmowy: {e}")
            import traceback
            traceback.print_exc()

    elif query.data == "quick_buy_credits":
        try:
            # Przekieruj do zakupu kredytów
            from handlers.payment_handler import payment_command
            
            # Utwórz sztuczny obiekt update
            fake_update = type('obj', (object,), {'effective_user': query.from_user, 'message': query.message})
            await payment_command(fake_update, context)
            return
        except Exception as e:
            print(f"Błąd przy przekierowaniu do zakupu kredytów: {e}")
            import traceback
            traceback.print_exc()
    
    # Fallback dla nieobsłużonych callbacków
    print(f"Nieobsłużony callback: {query.data}")
    try:
        keyboard = [[InlineKeyboardButton("⬅️ Menu główne", callback_data="menu_back_main")]]
        await update_menu(
            query,
            f"Nieznany przycisk. Spróbuj ponownie później.",
            InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Błąd przy wyświetlaniu komunikatu o nieobsłużonym callbacku: {e}")

async def handle_document_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles confirmation of document operations when cost warning was shown
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()
    
    if query.data.startswith("confirm_doc_analysis_"):
        # Extract document_id from callback data
        document_id = query.data[20:]
        
        # Check if document info is in context
        if ('user_data' not in context.chat_data or 
            user_id not in context.chat_data['user_data'] or
            'last_document_name' not in context.chat_data['user_data'][user_id]):
            
            await query.edit_message_text(
                create_header("Błąd operacji", "error") +
                "Nie znaleziono informacji o dokumencie. Spróbuj wysłać go ponownie.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        file_name = context.chat_data['user_data'][user_id]['last_document_name']
        
        # Inform the user that analysis has started
        await query.edit_message_text(
            create_status_indicator('loading', "Analizowanie dokumentu") + "\n\n" +
            f"*Dokument:* {file_name}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get operation cost
        credit_cost = CREDIT_COSTS["document"]
        
        # Check if the user still has enough credits
        credits = get_user_credits(user_id)
        if not check_user_credits(user_id, credit_cost):
            await query.edit_message_text(
                create_header("Brak wystarczających kredytów", "error") +
                "W międzyczasie twój stan kredytów zmienił się i nie masz już wystarczającej liczby kredytów.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store credits before the operation for reporting
        credits_before = credits
        
        # Pobierz plik
        try:
            file = await context.bot.get_file(document_id)
            file_bytes = await file.download_as_bytearray()
            
            # Analyze document
            analysis = await analyze_document(file_bytes, file_name)
            
            # Deduct credits
            deduct_user_credits(user_id, credit_cost, f"Analiza dokumentu: {file_name}")
            
            # Get credits after the operation
            credits_after = get_user_credits(user_id)
            
            # Prepare result message with styled header
            result_message = create_header(f"Analiza dokumentu: {file_name}", "document")
            
            # Add an excerpt from the analysis (first 3000 characters)
            analysis_excerpt = analysis[:3000]
            if len(analysis) > 3000:
                analysis_excerpt += "...\n\n(Analiza została skrócona ze względu na długość)"
            
            result_message += analysis_excerpt
            
            # Add credit usage report
            usage_report = format_credit_usage_report(
                "Analiza dokumentu", 
                credit_cost, 
                credits_before, 
                credits_after
            )
            result_message += f"\n\n{usage_report}"
            
            # Add a tip if appropriate
            if should_show_tip(user_id, context):
                tip = get_random_tip('document')
                result_message += f"\n\n💡 *Porada:* {tip}"
            
            # Update the message with analysis results
            await query.edit_message_text(
                result_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error analyzing document: {e}")
            await query.edit_message_text(
                create_header("Błąd analizy", "error") +
                "Wystąpił błąd podczas analizowania dokumentu. Spróbuj ponownie później.",
                parse_mode=ParseMode.MARKDOWN
            )

async def handle_photo_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles confirmation of photo operations when cost warning was shown
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()
    
    if query.data.startswith("confirm_photo_"):
        # Extract mode and photo_id from callback data
        parts = query.data.split("_")
        if len(parts) >= 4:
            mode = parts[2]
            photo_id = "_".join(parts[3:])
            
            # Check if photo info is in context
            if ('user_data' not in context.chat_data or 
                user_id not in context.chat_data['user_data'] or
                'last_photo_id' not in context.chat_data['user_data'][user_id]):
                
                await query.edit_message_text(
                    create_header("Błąd operacji", "error") +
                    "Nie znaleziono informacji o zdjęciu. Spróbuj wysłać je ponownie.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Get operation name and message
            if mode == "translate":
                operation_name = "Tłumaczenie tekstu ze zdjęcia"
                status_message = create_status_indicator('loading', "Tłumaczenie tekstu ze zdjęcia")
            else:
                operation_name = "Analiza zdjęcia"
                status_message = create_status_indicator('loading', "Analizowanie zdjęcia")
            
            # Inform the user that the operation has started
            await query.edit_message_text(
                status_message,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Get operation cost
            credit_cost = CREDIT_COSTS["photo"]
            
            # Check if the user still has enough credits
            credits = get_user_credits(user_id)
            if not check_user_credits(user_id, credit_cost):
                await query.edit_message_text(
                    create_header("Brak wystarczających kredytów", "error") +
                    "W międzyczasie twój stan kredytów zmienił się i nie masz już wystarczającej liczby kredytów.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Store credits before the operation for reporting
            credits_before = credits
            
            try:
                # Get the photo
                file = await context.bot.get_file(photo_id)
                file_bytes = await file.download_as_bytearray()
                
                # Analyze or translate the photo
                result = await analyze_image(file_bytes, f"photo_{photo_id}.jpg", mode=mode)
                
                # Deduct credits
                deduct_user_credits(user_id, credit_cost, operation_name)
                
                # Get credits after the operation
                credits_after = get_user_credits(user_id)
                
                # Prepare result message with styled header
                if mode == "translate":
                    result_message = create_header("Tłumaczenie tekstu ze zdjęcia", "translation")
                else:
                    result_message = create_header("Analiza zdjęcia", "analysis")
                
                # Add the result
                result_message += result
                
                # Add credit usage report
                usage_report = format_credit_usage_report(
                    operation_name, 
                    credit_cost, 
                    credits_before, 
                    credits_after
                )
                result_message += f"\n\n{usage_report}"
                
                # Add a tip if appropriate
                if should_show_tip(user_id, context):
                    tip = get_random_tip('document')
                    result_message += f"\n\n💡 *Porada:* {tip}"
                
                # Update the message with results
                await query.edit_message_text(
                    result_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Error processing photo: {e}")
                await query.edit_message_text(
                    create_header("Błąd operacji", "error") +
                    f"Wystąpił błąd podczas {operation_name.lower()}. Spróbuj ponownie później.",
                    parse_mode=ParseMode.MARKDOWN
                )
    
    elif query.data == "cancel_operation":
        # User canceled the operation
        await query.edit_message_text(
            create_header("Operacja anulowana", "info") +
            "Operacja została anulowana.",
            parse_mode=ParseMode.MARKDOWN
        )

# Dodaj dedykowaną funkcję tylko dla tego przycisku
async def handle_buy_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje przycisk zakupu kredytów"""
    query = update.callback_query
    await query.answer()
    
    # Pokaż podstawowe menu zakupu
    message = "🛒 *Zakup kredytów*\n\nWybierz pakiet kredytów:"
    
    # Pobierz pakiety
    from config import CREDIT_PACKAGES
    
    # Stwórz przyciski dla pakietów
    keyboard = []
    for pkg in CREDIT_PACKAGES:
        keyboard.append([
            InlineKeyboardButton(
                f"{pkg['name']} - {pkg['credits']} kredytów ({pkg['price']} PLN)", 
                callback_data=f"buy_package_{pkg['id']}"
            )
        ])
    
    # Dodaj przycisk powrotu
    keyboard.append([
        InlineKeyboardButton("⬅️ Powrót", callback_data="menu_back_main")
    ])
    
    try:
        await query.edit_message_text(
            text=message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Error updating message: {e}")

# Zarejestruj ten handler przed ogólnym handlerem
application.add_handler(CallbackQueryHandler(
    handle_buy_credits, 
    pattern="^menu_credits_buy$"
))

async def handle_buy_credits_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje wszystkie przyciski zakupu kredytów"""
    query = update.callback_query
    await query.answer()
    
    # Przekieruj na stronę zakupu kredytów
    await buy_command(update, context)

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje wszystkie nieznane callbacki"""
    query = update.callback_query
    await query.answer("Ta funkcja jest w trakcie implementacji")
    
    # Logowanie nieznanego callbacka
    print(f"Nieobsłużony callback: {query.data}")
    
    # Informacja dla użytkownika
    try:
        await query.edit_message_text(
            f"Funkcja '{query.data}' jest w trakcie implementacji.\n\nWróć do menu głównego i spróbuj innej opcji.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Powrót do menu", callback_data="menu_back_main")
            ]])
        )
    except Exception as e:
        print(f"Błąd przy edycji wiadomości: {e}")

async def handle_message_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles confirmation of AI message when cost warning was shown
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()
    
    if query.data == "confirm_message":
        # Check if there's a pending message
        if ('user_data' not in context.chat_data or 
            user_id not in context.chat_data['user_data'] or 
            'pending_message' not in context.chat_data['user_data'][user_id]):
            
            await query.edit_message_text(
                create_header("Błąd operacji", "error") +
                "Nie znaleziono oczekującej wiadomości. Spróbuj ponownie.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Get the pending message
        user_message = context.chat_data['user_data'][user_id]['pending_message']
        
        # Delete confirmation message to avoid clutter
        await query.message.delete()
        
        # Update loading status
        status_message = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=create_status_indicator('loading', "Generowanie odpowiedzi"),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Determine mode and credit cost (same logic as in message_handler)
        current_mode = "no_mode"
        credit_cost = 1
        
        if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
            user_data = context.chat_data['user_data'][user_id]
            if 'current_mode' in user_data and user_data['current_mode'] in CHAT_MODES:
                current_mode = user_data['current_mode']
                credit_cost = CHAT_MODES[current_mode]["credit_cost"]
        
        # Get or create conversation
        try:
            conversation = get_active_conversation(user_id)
            conversation_id = conversation['id']
        except Exception as e:
            print(f"Błąd przy pobieraniu konwersacji: {e}")
            await status_message.edit_text(
                create_header("Błąd konwersacji", "error") +
                "Wystąpił błąd przy pobieraniu konwersacji. Spróbuj ponownie.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Save user message to database
        try:
            save_message(conversation_id, user_id, user_message, is_from_user=True)
        except Exception as e:
            print(f"Błąd przy zapisie wiadomości użytkownika: {e}")
        
        # Get conversation history
        try:
            history = get_conversation_history(conversation_id, limit=MAX_CONTEXT_MESSAGES)
        except Exception as e:
            print(f"Błąd przy pobieraniu historii: {e}")
            history = []
        
        # Determine model to use
        model_to_use = CHAT_MODES[current_mode].get("model", DEFAULT_MODEL)
        
        # If user selected a specific model, use it
        if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
            user_data = context.chat_data['user_data'][user_id]
            if 'current_model' in user_data:
                model_to_use = user_data['current_model']
                # Update credit cost based on model
                credit_cost = CREDIT_COSTS["message"].get(model_to_use, CREDIT_COSTS["message"]["default"])
        
        # Prepare system prompt from selected mode
        system_prompt = CHAT_MODES[current_mode]["prompt"]
        
        # Prepare messages for OpenAI API
        messages = prepare_messages_from_history(history, user_message, system_prompt)
        
        # Store credits before operation
        credits_before = get_user_credits(user_id)
        
        # Generate response
        full_response = ""
        buffer = ""
        last_update = datetime.datetime.now().timestamp()
        
        try:
            # Update message with starting response
            response_message = await status_message.edit_text(
                create_header("Odpowiedź AI", "chat"),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Stream the response
            async for chunk in chat_completion_stream(messages, model=model_to_use):
                full_response += chunk
                buffer += chunk
                
                # Update message periodically
                current_time = datetime.datetime.now().timestamp()
                if current_time - last_update >= 1.0 or len(buffer) > 100:
                    try:
                        await response_message.edit_text(
                            create_header("Odpowiedź AI", "chat") + full_response + "▌",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        buffer = ""
                        last_update = current_time
                    except Exception as e:
                        print(f"Błąd przy aktualizacji wiadomości: {e}")
            
            # Final update without cursor
            try:
                await response_message.edit_text(
                    create_header("Odpowiedź AI", "chat") + full_response,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                print(f"Błąd formatowania Markdown: {e}")
                await response_message.edit_text(
                    create_header("Odpowiedź AI", "chat") + full_response,
                    parse_mode=None
                )
            
            # Save response to database
            save_message(conversation_id, user_id, full_response, is_from_user=False, model_used=model_to_use)
            
            # Deduct credits
            deduct_user_credits(user_id, credit_cost, 
                               get_text("message_model", language, model=model_to_use, default=f"Wiadomość ({model_to_use})"))
            
            # Get credits after operation
            credits_after = get_user_credits(user_id)
            
            # Display credit usage report
            usage_report = format_credit_usage_report(
                "Wiadomość AI", 
                credit_cost, 
                credits_before, 
                credits_after
            )
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=usage_report,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Check for low credits
            if credits_after < 5:
                low_credits_warning = create_header("Niski stan kredytów", "warning")
                low_credits_warning += f"Pozostało Ci tylko *{credits_after}* kredytów. Rozważ zakup pakietu, aby kontynuować korzystanie z bota."
                
                # Add buttons to buy credits
                keyboard = [[InlineKeyboardButton("💳 " + get_text("buy_credits_btn", language), callback_data="menu_credits_buy")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=low_credits_warning,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            
            # Add tip if appropriate
            tip = get_contextual_tip('chat', context, user_id)
            if tip:
                tip_message = f"💡 *Porada:* {tip}"
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=tip_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Increment message counter
            increment_messages_used(user_id)
            
        except Exception as e:
            print(f"Wystąpił błąd podczas generowania odpowiedzi: {e}")
            await status_message.edit_text(
                create_header("Błąd odpowiedzi", "error") +
                get_text("response_error", language, error=str(e)),
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif query.data == "cancel_operation":
        # User canceled the message
        await query.edit_message_text(
            create_header("Operacja anulowana", "info") +
            "Wysłanie wiadomości zostało anulowane.",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_back_to_main(update, context):
    """Obsługuje powrót do głównego menu"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Pobierz tekst powitalny
    welcome_text = "Menu główne"
    
    # Utwórz klawiaturę menu
    keyboard = [
        [
            InlineKeyboardButton("💬 Tryby czatu", callback_data="menu_section_chat_modes"),
            InlineKeyboardButton("🖼️ Generowanie obrazów", callback_data="menu_image_generate")
        ],
        [
            InlineKeyboardButton("💰 Kredyty", callback_data="menu_section_credits"),
            InlineKeyboardButton("📚 Historia", callback_data="menu_section_history")
        ],
        [
            InlineKeyboardButton("⚙️ Ustawienia", callback_data="menu_section_settings"),
            InlineKeyboardButton("❓ Pomoc", callback_data="menu_help")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Uproszczona metoda - zawsze próbuje edytować tekst zamiast bardziej złożonej logiki
    try:
        await query.edit_message_text(
            text=welcome_text,
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        print(f"Error updating message: {e}")
        return False

async def handle_image_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles confirmation of image generation when cost warning was shown
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    await query.answer()
    
    if query.data.startswith("confirm_image_"):
        # Extract prompt from callback data
        prompt = query.data[14:].replace('_', ' ')
        
        # Inform the user that image generation has started
        await query.edit_message_text(
            create_status_indicator('loading', "Generowanie obrazu") + "\n\n" +
            f"*Prompt:* {prompt}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Get quality and cost
        quality = "standard"
        credit_cost = CREDIT_COSTS["image"][quality]
        
        # Check if the user still has enough credits
        credits = get_user_credits(user_id)
        if not check_user_credits(user_id, credit_cost):
            await query.edit_message_text(
                create_header("Brak wystarczających kredytów", "error") +
                "W międzyczasie twój stan kredytów zmienił się i nie masz już wystarczającej liczby kredytów.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store credits before the operation for reporting
        credits_before = credits
        
        # Generate image
        image_url = await generate_image_dall_e(prompt)
        
        # Deduct credits
        deduct_user_credits(user_id, credit_cost, get_text("image_generation", language, default="Generowanie obrazu"))
        
        # Get credits after the operation
        credits_after = get_user_credits(user_id)
        
        if image_url:
            # Prepare a caption with usage report
            caption = create_header("Wygenerowany obraz", "image")
            caption += f"*Prompt:* {prompt}\n"
            
            # Add credit usage report
            usage_report = format_credit_usage_report(
                "Generowanie obrazu", 
                credit_cost, 
                credits_before, 
                credits_after
            )
            caption += f"\n{usage_report}"
            
            # Add a tip if appropriate
            if should_show_tip(user_id, context):
                tip = get_random_tip('image')
                caption += f"\n\n💡 *Porada:* {tip}"
            
            # Delete the confirmation message
            await query.message.delete()
            
            # Send the image
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Update with error message
            await query.edit_message_text(
                create_header("Błąd generowania", "error") +
                get_text("image_generation_error", language, default="Przepraszam, wystąpił błąd podczas generowania obrazu. Spróbuj ponownie z innym opisem."),
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif query.data == "cancel_operation":
        # User canceled the operation
        await query.edit_message_text(
            create_header("Operacja anulowana", "info") +
            "Generowanie obrazu zostało anulowane.",
            parse_mode=ParseMode.MARKDOWN
        )

# Rejestracja handlerów komend
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("status", check_status))
application.add_handler(CommandHandler("newchat", new_chat))
application.add_handler(CommandHandler("restart", restart_command))
application.add_handler(CommandHandler("mode", show_modes))
application.add_handler(CommandHandler("image", generate_image))
application.add_handler(CommandHandler("export", export_conversation))
application.add_handler(CommandHandler("language", language_command))
application.add_handler(CommandHandler("onboarding", onboarding_command))
application.add_handler(CommandHandler("translate", translate_command))

application.add_handler(CallbackQueryHandler(
    handle_image_confirmation, pattern="^confirm_image_"
))

application.add_handler(CallbackQueryHandler(
    handle_message_confirmation, 
    pattern="^confirm_message$|^cancel_operation$"
))

application.add_handler(CallbackQueryHandler(handle_unknown_callback))


# Handlery kredytów i płatności
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CommandHandler("creditstats", credit_stats_command))
application.add_handler(CommandHandler("payment", payment_command))
application.add_handler(CommandHandler("subscription", subscription_command))
application.add_handler(CommandHandler("code", code_command))

# Handle image and document confirmations
application.add_handler(CallbackQueryHandler(
    handle_image_confirmation, pattern="^confirm_image_"
))
application.add_handler(CallbackQueryHandler(
    lambda update, context: handle_document_confirmation(update, context), 
    pattern="^confirm_doc_"
))

# Handlery dla administratorów
application.add_handler(CommandHandler("addpackage", add_package))
application.add_handler(CommandHandler("listpackages", list_packages))
application.add_handler(CommandHandler("togglepackage", toggle_package))
application.add_handler(CommandHandler("adddefaultpackages", add_default_packages))
application.add_handler(CommandHandler("gencode", admin_generate_code))

# Handler wiadomości tekstowych
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

# Handler dokumentów
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

application.add_handler(CallbackQueryHandler(
    handle_photo_confirmation, 
    pattern="^confirm_photo_|^cancel_operation$"
))

application.add_handler(CallbackQueryHandler(
    handle_credit_callback, pattern="^(credits_|menu_credits_|buy_)"
))

# Handler zdjęć
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# Handler dla callbacków (przycisków)
application.add_handler(CallbackQueryHandler(handle_callback_query))

# Uruchomienie bota
if __name__ == "__main__":
    print("Bot uruchomiony. Naciśnij Ctrl+C, aby zatrzymać.")
    application.run_polling()