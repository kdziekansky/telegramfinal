from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import CHAT_MODES, AVAILABLE_LANGUAGES, AVAILABLE_MODELS, CREDIT_COSTS, DEFAULT_MODEL, BOT_NAME
from utils.translations import get_text
from database.credits_client import get_user_credits
from database.supabase_client import update_user_language
from database.credits_client import get_user_credits, get_credit_packages
from config import BOT_NAME

# ==================== FUNKCJE POMOCNICZE DO ZARZĄDZANIA DANYMI UŻYTKOWNIKA ====================

def get_user_language(context, user_id):
    """Pobiera język użytkownika z kontekstu lub bazy danych"""
    # Sprawdź, czy język jest zapisany w kontekście
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data'] and 'language' in context.chat_data['user_data'][user_id]:
        return context.chat_data['user_data'][user_id]['language']
    
    # Jeśli nie, pobierz z bazy danych Supabase
    try:
        from database.supabase_client import supabase
        
        # Sprawdź najpierw kolumnę 'language'
        response = supabase.table('users').select('language, language_code').eq('id', user_id).execute()
        
        if response.data:
            user_data = response.data[0]
            language = user_data.get('language')
            
            # Jeśli nie ma language, użyj language_code
            if not language:
                language = user_data.get('language_code')
            
            if language:
                # Zapisz w kontekście na przyszłość
                if 'user_data' not in context.chat_data:
                    context.chat_data['user_data'] = {}
                
                if user_id not in context.chat_data['user_data']:
                    context.chat_data['user_data'][user_id] = {}
                
                context.chat_data['user_data'][user_id]['language'] = language
                return language
    except Exception as e:
        print(f"Błąd pobierania języka z bazy: {e}")
    
    # Domyślny język, jeśli nie znaleziono w bazie
    return "pl"

def generate_navigation_bar(current_path, language):
    """
    Generuje tekst paska nawigacyjnego
    
    Args:
        current_path (str): Aktualna ścieżka nawigacji, np. "Main > Credits"
        language (str): Kod języka
        
    Returns:
        str: Tekst paska nawigacyjnego
    """
    if not current_path:
        return get_text("main_menu", language, default="Menu główne")
    
    return current_path

def get_user_current_mode(context, user_id):
    """Pobiera aktualny tryb czatu użytkownika"""
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_mode' in user_data and user_data['current_mode'] in CHAT_MODES:
            return user_data['current_mode']
    return "no_mode"

def get_user_current_model(context, user_id):
    """Pobiera aktualny model AI użytkownika"""
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data']:
        user_data = context.chat_data['user_data'][user_id]
        if 'current_model' in user_data and user_data['current_model'] in AVAILABLE_MODELS:
            return user_data['current_model']
    return DEFAULT_MODEL  # Domyślny model

def store_menu_state(context, user_id, state, message_id=None):
    """
    Zapisuje stan menu dla użytkownika
    
    Args:
        context: Kontekst bota
        user_id: ID użytkownika
        state: Stan menu (np. 'main', 'settings', 'chat_modes')
        message_id: ID wiadomości menu (opcjonalnie)
    """
    if 'user_data' not in context.chat_data:
        context.chat_data['user_data'] = {}
    
    if user_id not in context.chat_data['user_data']:
        context.chat_data['user_data'][user_id] = {}
    
    context.chat_data['user_data'][user_id]['menu_state'] = state
    
    if message_id:
        context.chat_data['user_data'][user_id]['menu_message_id'] = message_id

def get_menu_state(context, user_id):
    """
    Pobiera stan menu dla użytkownika
    
    Args:
        context: Kontekst bota
        user_id: ID użytkownika
        
    Returns:
        str: Stan menu lub 'main' jeśli brak
    """
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data'] and 'menu_state' in context.chat_data['user_data'][user_id]:
        return context.chat_data['user_data'][user_id]['menu_state']
    return 'main'

def get_menu_message_id(context, user_id):
    """
    Pobiera ID wiadomości menu dla użytkownika
    
    Args:
        context: Kontekst bota
        user_id: ID użytkownika
        
    Returns:
        int: ID wiadomości lub None jeśli brak
    """
    if 'user_data' in context.chat_data and user_id in context.chat_data['user_data'] and 'menu_message_id' in context.chat_data['user_data'][user_id]:
        return context.chat_data['user_data'][user_id]['menu_message_id']
    return None

# ==================== FUNKCJE GENERUJĄCE UKŁADY MENU ====================

def create_main_menu_markup(language):
    """Tworzy klawiaturę dla głównego menu"""
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
        ],
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def create_chat_modes_markup(language):
    """Tworzy klawiaturę dla menu trybów czatu"""
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
                f"{mode_name} ({mode_info['credit_cost']} {credit_text})", 
                callback_data=f"mode_{mode_id}"
            )
        ])
    
    # Pasek szybkiego dostępu
    keyboard.append([
        InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
        InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
        InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
    ])
    
    # Dodaj przycisk powrotu w jednolitym miejscu
    keyboard.append([
        InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def create_credits_menu_markup(language):
    """Tworzy klawiaturę dla menu kredytów"""
    keyboard = [
        [InlineKeyboardButton(get_text("check_balance", language), callback_data="menu_credits_check")],
        [InlineKeyboardButton(get_text("buy_credits_btn", language), callback_data="menu_credits_buy")],
        
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat")
        ],
        
        # Przycisk "Wstecz"
        [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_settings_menu_markup(language):
    """Tworzy klawiaturę dla menu ustawień"""
    keyboard = [
        [InlineKeyboardButton(get_text("settings_model", language), callback_data="settings_model")],
        [InlineKeyboardButton(get_text("settings_language", language), callback_data="settings_language")],
        [InlineKeyboardButton(get_text("settings_name", language), callback_data="settings_name")],
        
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ],
        
        # Przycisk "Wstecz"
        [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_history_menu_markup(language):
    """Tworzy klawiaturę dla menu historii"""
    keyboard = [
        [InlineKeyboardButton(get_text("new_chat", language), callback_data="history_new")],
        [InlineKeyboardButton(get_text("view_history", language), callback_data="history_view")],
        [InlineKeyboardButton(get_text("delete_history", language), callback_data="history_delete")],
        
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ],
        
        # Przycisk "Wstecz"
        [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_model_selection_markup(language):
    """Tworzy klawiaturę dla wyboru modelu AI"""
    keyboard = []
    for model_id, model_name in AVAILABLE_MODELS.items():
        # Dodaj informację o koszcie kredytów
        credit_cost = CREDIT_COSTS["message"].get(model_id, CREDIT_COSTS["message"]["default"])
        keyboard.append([
            InlineKeyboardButton(
                text=f"{model_name} ({credit_cost} {get_text('credits_per_message', language)})", 
                callback_data=f"model_{model_id}"
            )
        ])
    
    # Dodaj przycisk powrotu
    keyboard.append([
        InlineKeyboardButton(get_text("back", language), callback_data="menu_section_settings")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def create_language_selection_markup(language):
    """Tworzy klawiaturę dla wyboru języka"""
    keyboard = []
    for lang_code, lang_name in AVAILABLE_LANGUAGES.items():
        keyboard.append([
            InlineKeyboardButton(
                lang_name, 
                callback_data=f"start_lang_{lang_code}"
            )
        ])
    
    # Dodaj przycisk powrotu
    keyboard.append([
        InlineKeyboardButton(get_text("back", language), callback_data="menu_section_settings")
    ])
    
    return InlineKeyboardMarkup(keyboard)

# ==================== FUNKCJE POMOCNICZE DO AKTUALIZACJI WIADOMOŚCI ====================

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
        # Sprawdzamy, czy wiadomość ma caption (jest zdjęciem lub innym typem mediów)
        has_caption = hasattr(query.message, 'caption') and query.message.caption is not None
        
        if has_caption:
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
        
        # Ostatnia szansa - stwórz nową wiadomość zamiast edytować istniejącą
        try:
            await query.message.delete()
            message = await query.message.chat.send_message(
                text=caption_or_text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            
            # Jeśli funkcja store_menu_state jest dostępna, zapisz ID nowej wiadomości
            if 'store_menu_state' in globals():
                store_menu_state(context, user_id, menu_state, message.message_id)
            
            return True
        except Exception as e3:
            print(f"Trzeci błąd aktualizacji wiadomości: {e3}")
            return False

# ==================== FUNKCJE OBSŁUGUJĄCE POSZCZEGÓLNE SEKCJE MENU ====================

async def handle_chat_modes_section(update, context, navigation_path=""):
    """Obsługuje sekcję trybów czatu"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += get_text("select_chat_mode", language)
    
    reply_markup = create_chat_modes_markup(language)
    result = await update_message(
        query, 
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'chat_modes')
    
    return result

async def handle_credits_section(update, context, navigation_path=""):
    """Obsługuje sekcję kredytów"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += f"{get_text('credits_status', language, credits=get_user_credits(user_id))}\n\n{get_text('credit_options', language)}"
    reply_markup = create_credits_menu_markup(language)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'credits')
    
    return result

async def handle_history_section(update, context, navigation_path=""):
    """Obsługuje sekcję historii"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += get_text("history_options", language) + "\n\n" + get_text("export_info", language, default="Aby wyeksportować konwersację, użyj komendy /export")
    reply_markup = create_history_menu_markup(language)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'history')
    
    return result

async def handle_settings_section(update, context, navigation_path=""):
    """Obsługuje sekcję ustawień"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += get_text("settings_options", language)
    reply_markup = create_settings_menu_markup(language)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'settings')
    
    return result

async def handle_help_section(update, context, navigation_path=""):
    """Obsługuje sekcję pomocy"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += get_text("help_text", language)
    keyboard = [
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ],
        [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'help')
    
    return result

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obsługuje komendę /help
    Wyświetla informacje pomocnicze o bocie z nowym interfejsem
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Pobierz tekst pomocy z tłumaczeń
    help_text = get_text("help_text", language)
    
    # Dodaj klawiaturę z przyciskami szybkiego dostępu i powrotem do menu
    keyboard = [
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ],
        [InlineKeyboardButton("⬅️ " + get_text("back_to_main_menu", language, default="Powrót do menu głównego"), callback_data="menu_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Próba wysłania z formatowaniem Markdown
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    except Exception as e:
        # W przypadku błędu, spróbuj wysłać bez formatowania
        print(f"Błąd formatowania Markdown w help_command: {e}")
        try:
            await update.message.reply_text(
                help_text,
                reply_markup=reply_markup
            )
        except Exception as e2:
            print(f"Drugi błąd w help_command: {e2}")
            # Ostateczna próba - wysłanie uproszczonego tekstu pomocy
            simple_help = "Pomoc i informacje o bocie. Dostępne komendy: /start, /credits, /buy, /status, /newchat, /mode, /image, /restart, /help, /code."
            await update.message.reply_text(
                simple_help,
                reply_markup=reply_markup
            )

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sprawdza status konta użytkownika z nowym interfejsem
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
        [InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes")],
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat")
        ],
        [InlineKeyboardButton("⬅️ " + get_text("back_to_main_menu", language, default="Powrót do menu głównego"), callback_data="menu_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        print(f"Błąd formatowania w check_status: {e}")
        # Próba wysłania bez formatowania
        await update.message.reply_text(message, reply_markup=reply_markup)

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rozpoczyna nową konwersację z ulepszonym interfejsem"""
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Utwórz nową konwersację
    conversation = create_new_conversation(user_id)
    
    if conversation:
        # Dodaj przyciski menu dla łatwiejszej nawigacji
        keyboard = [
            [InlineKeyboardButton(get_text("menu_chat_mode", language), callback_data="menu_section_chat_modes")],
            [InlineKeyboardButton(get_text("menu_credits", language), callback_data="menu_section_credits")],
            # Pasek szybkiego dostępu
            [
                InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
                InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
            ],
            [InlineKeyboardButton("⬅️ " + get_text("back_to_main_menu", language, default="Powrót do menu głównego"), callback_data="menu_back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            get_text("newchat_command", language),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            get_text("new_chat_error", language),
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_callback_error(query, error_message, full_error=None, show_retry=True, language=None):
    """
    Ulepszona obsługa błędów podczas przetwarzania callbacków
    
    Args:
        query: Obiekt callback_query
        error_message: Krótka wiadomość o błędzie dla użytkownika
        full_error: Pełny tekst błędu do zalogowania (opcjonalnie)
        show_retry: Czy pokazać przycisk ponowienia próby (opcjonalnie)
        language: Kod języka (opcjonalnie)
    """
    if full_error:
        print(f"Błąd podczas obsługi callbacku: {full_error}")
        import traceback
        traceback.print_exc()
    
    # Próba pobrania języka, jeśli nie został przekazany
    if not language:
        try:
            user_id = query.from_user.id
            # Spróbuj pobrać język z kontekstu
            if hasattr(query, 'bot') and hasattr(query.bot, 'context'):
                context = query.bot.context
                language = get_user_language(context, user_id)
            else:
                # Jeśli nie udało się pobrać języka, użyj domyślnego
                language = "pl"
        except:
            language = "pl"
    
    # Powiadom użytkownika o błędzie przez notyfikację
    try:
        await query.answer(error_message)
    except Exception:
        pass
    
    # Przygotuj klawiaturę z przyciskami
    keyboard = []
    
    # Dodaj przycisk ponowienia próby, jeśli wymagane
    if show_retry:
        keyboard.append([
            InlineKeyboardButton(
                get_text("retry", language, default="Spróbuj ponownie"),
                callback_data=query.data
            )
        ])
    
    # Dodaj pasek szybkiego dostępu
    keyboard.append([
        InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
        InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
        InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
    ])
    
    # Dodaj przycisk powrotu do menu głównego
    keyboard.append([
        InlineKeyboardButton("⬅️ " + get_text("back_to_main_menu", language, default="Powrót do menu głównego"), callback_data="menu_back_main")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Spróbuj zaktualizować wiadomość z informacją o błędzie
    try:
        error_text = f"⚠️ {error_message}\n\n{get_text('error_retry', language, default='Możesz spróbować ponownie lub wrócić do menu głównego.')}"
        
        if hasattr(query.message, 'caption'):
            await query.edit_message_caption(
                caption=error_text,
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                text=error_text,
                reply_markup=reply_markup
            )
    except Exception:
        # Jeśli nie udało się zaktualizować wiadomości, spróbuj wysłać nową
        try:
            await query.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⚠️ {error_message}\n\n{get_text('error_retry', language, default='Możesz spróbować ponownie lub wrócić do menu głównego.')}",
                reply_markup=reply_markup
            )
        except Exception:
            # Jeśli i to się nie udało, nie rób nic
            pass

async def handle_image_section(update, context, navigation_path=""):
    """Obsługuje sekcję generowania obrazów"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Dodajemy pasek nawigacyjny do tekstu, jeśli podano
    message_text = ""
    if navigation_path:
        message_text = f"*{navigation_path}*\n\n"
    
    message_text += get_text("image_usage", language)
    keyboard = [
        # Pasek szybkiego dostępu
        [
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat"),
            InlineKeyboardButton("💸 " + get_text("buy_credits_btn", language, default="Kup kredyty"), callback_data="quick_buy_credits")
        ],
        [InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'image')
    
    return result

async def handle_back_to_main(update, context):
    """Obsługuje powrót do głównego menu"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Pobierz bogaty tekst powitalny
    welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
    keyboard = create_main_menu_markup(language)
    
    # Używamy funkcji update_message zamiast tworzenia nowej wiadomości
    await update_message(
        query,
        welcome_text,
        keyboard,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz stan menu
    store_menu_state(context, user_id, 'main')
    
    return True

async def handle_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje wybór modelu AI"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    print(f"Obsługa wyboru modelu dla użytkownika {user_id}")
    
    reply_markup = create_model_selection_markup(language)
    result = await update_message(
        query, 
        get_text("settings_choose_model", language),
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return result

async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje wybór języka"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    print(f"Obsługa wyboru języka dla użytkownika {user_id}")
    
    reply_markup = create_language_selection_markup(language)
    result = await update_message(
        query,
        get_text("settings_choose_language", language),
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return result

async def handle_name_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługuje ustawienia nazwy użytkownika"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    print(f"Obsługa ustawień nazwy dla użytkownika {user_id}")
    
    message_text = get_text("settings_change_name", language, default="Aby zmienić swoją nazwę, użyj komendy /setname [twoja_nazwa].\n\nNa przykład: /setname Jan Kowalski")
    keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_section_settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    result = await update_message(
        query,
        message_text,
        reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return result

async def handle_history_view(update, context):
    """Obsługuje wyświetlanie historii"""
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
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
        
        await update_message(
            query,
            message_text,
            reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    
    # Pobierz historię konwersacji
    history = get_conversation_history(conversation['id'])
    
    if not history:
        # Informacja przez notyfikację
        await query.answer(get_text("history_empty", language))
        
        # Wyświetl komunikat również w wiadomości
        message_text = get_text("history_empty", language)
        keyboard = [[InlineKeyboardButton(get_text("back", language), callback_data="menu_section_history")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update_message(
            query,
            message_text,
            reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    
    # Przygotuj tekst z historią
    message_text = f"*{get_text('history_title', language)}*\n\n"
    
    for i, msg in enumerate(history[-10:]):  # Ostatnie 10 wiadomości
        sender = get_text("history_user", language) if msg['is_from_user'] else get_text("history_bot", language)
        
        # Skróć treść wiadomości, jeśli jest zbyt długa
        content = msg['content']
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
        await update_message(
            query,
            message_text,
            reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Błąd formatowania historii: {e}")
        # Spróbuj bez formatowania
        plain_message = message_text.replace("*", "").replace("**", "")
        await update_message(
            query,
            plain_message,
            reply_markup
        )
    
    return True

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
    
    # Lista kroków onboardingu - USUNIĘTE NIEDZIAŁAJĄCE FUNKCJE
    steps = [
        'welcome', 'chat', 'modes', 'images', 'analysis', 
        'credits', 'referral', 'export', 'settings', 'finish'
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
        reply_markup=reply_markup
    )

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

# ==================== GŁÓWNE FUNKCJE MENU ====================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Wyświetla główne menu bota z przyciskami inline
    """
    user_id = update.effective_user.id
    
    # Upewnij się, że klawiatura systemowa jest usunięta
    await update.message.reply_text("Usuwam klawiaturę...", reply_markup=ReplyKeyboardRemove())
    
    # Pobierz język użytkownika
    language = get_user_language(context, user_id)
    
    # Przygotuj tekst powitalny
    welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
    
    # Utwórz klawiaturę menu
    reply_markup = create_main_menu_markup(language)
    
    # Wyślij menu
    message = await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Zapisz ID wiadomości menu i stan menu
    store_menu_state(context, user_id, 'main', message.message_id)

async def update_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, menu_state, markup=None, navigation_path=""):
    """
    Aktualizuje istniejące menu
    
    Args:
        update: Obiekt Update
        context: Kontekst bota
        menu_state: Nowy stan menu
        markup: Klawiatura menu (opcjonalnie)
        navigation_path: Ścieżka nawigacji (opcjonalnie)
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Obsługa różnych stanów menu
    if menu_state == 'main':
        # Używamy welcome_message
        welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
        menu_text = welcome_text
        
        if not markup:
            markup = create_main_menu_markup(language)
            
        await update_message(query, menu_text, markup, parse_mode=ParseMode.MARKDOWN)
    elif menu_state == 'chat_modes':
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_chat_mode", language)
        await handle_chat_modes_section(update, context, nav_path)
    elif menu_state == 'credits':
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_credits", language)
        await handle_credits_section(update, context, nav_path)
    elif menu_state == 'history':
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_dialog_history", language)
        await handle_history_section(update, context, nav_path)
    elif menu_state == 'settings':
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_settings", language)
        await handle_settings_section(update, context, nav_path)
    else:
        # Domyślnie też używamy welcome_message
        welcome_text = get_text("welcome_message", language, bot_name=BOT_NAME)
        menu_text = welcome_text
        
        if not markup:
            markup = create_main_menu_markup(language)
            
        await update_message(query, menu_text, markup, parse_mode=ParseMode.MARKDOWN)
    
    # Zapisz nowy stan menu
    store_menu_state(context, user_id, menu_state)

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obsługuje wszystkie callbacki związane z menu
    
    Returns:
        bool: True jeśli callback został obsłużony, False w przeciwnym razie
    """
    query = update.callback_query
    user_id = query.from_user.id
    language = get_user_language(context, user_id)
    
    # Sekcje menu
    if query.data == "menu_section_chat_modes":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_chat_mode", language)
        return await handle_chat_modes_section(update, context, nav_path)
    elif query.data == "menu_section_credits":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_credits", language)
        return await handle_credits_section(update, context, nav_path)
    elif query.data == "menu_section_history":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_dialog_history", language)
        return await handle_history_section(update, context, nav_path)
    elif query.data == "menu_section_settings":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_settings", language)
        return await handle_settings_section(update, context, nav_path)
    elif query.data == "menu_help":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_help", language)
        return await handle_help_section(update, context, nav_path)
    elif query.data == "menu_image_generate":
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("image_generate", language)
        return await handle_image_section(update, context, nav_path)
    elif query.data == "menu_back_main":
        return await handle_back_to_main(update, context)
    
    # Przyciski szybkiego dostępu
    elif query.data == "quick_new_chat":
        # Utwórz nową konwersację
        from database.supabase_client import create_new_conversation
        conversation = create_new_conversation(user_id)
        
        await query.answer(get_text("new_chat_created", language, default="Utworzono nową rozmowę"))
        
        # Wróć do głównego menu
        return await handle_back_to_main(update, context)
    elif query.data == "quick_last_chat":
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
            
            return await handle_back_to_main(update, context)
        
        return True
    elif query.data == "quick_buy_credits":
        # Przekieruj do zakupu kredytów
        nav_path = get_text("main_menu", language, default="Menu główne") + " > " + get_text("menu_credits", language) + " > " + get_text("buy_credits_btn", language)
        
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
        
        # Pasek szybkiego dostępu
        keyboard.append([
            InlineKeyboardButton("🆕 " + get_text("new_chat", language, default="Nowa rozmowa"), callback_data="quick_new_chat"),
            InlineKeyboardButton("💬 " + get_text("last_chat", language, default="Ostatnia rozmowa"), callback_data="quick_last_chat")
        ])
        
        # Dodaj przycisk powrotu
        keyboard.append([
            InlineKeyboardButton("⬅️ " + get_text("back", language), callback_data="menu_section_credits")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Tekst informacyjny o zakupie kredytów z paskiem nawigacyjnym
        message = f"*{nav_path}*\n\n" + get_text("buy_credits", language, packages=packages_text)
        
        await update_message(
            query,
            message,
            reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return True

    # Jeśli dotarliśmy tutaj, oznacza to, że callback nie został obsłużony
    return False

async def set_user_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ustawia nazwę użytkownika
    Użycie: /setname [nazwa]
    """
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)
    
    # Sprawdź, czy podano argumenty
    if not context.args or len(' '.join(context.args)) < 1:
        await update.message.reply_text(
            get_text("settings_change_name", language),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Połącz argumenty, aby utworzyć nazwę
    new_name = ' '.join(context.args)
    
    # Ogranicz długość nazwy
    if len(new_name) > 50:
        new_name = new_name[:47] + "..."
    
    try:
        # Aktualizuj nazwę użytkownika w bazie danych Supabase
        from database.supabase_client import supabase
        
        response = supabase.table('users').update(
            {"first_name": new_name}
        ).eq('id', user_id).execute()
        
        # Aktualizuj nazwę w kontekście, jeśli istnieje
        if 'user_data' not in context.chat_data:
            context.chat_data['user_data'] = {}
        
        if user_id not in context.chat_data['user_data']:
            context.chat_data['user_data'][user_id] = {}
        
        context.chat_data['user_data'][user_id]['name'] = new_name
        
        # Potwierdź zmianę nazwy
        await update.message.reply_text(
            f"{get_text('name_changed', language)} *{new_name}*",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print(f"Błąd przy zmianie nazwy użytkownika: {e}")
        await update.message.reply_text(
            "Wystąpił błąd podczas zmiany nazwy. Spróbuj ponownie później.",
            parse_mode=ParseMode.MARKDOWN
        )