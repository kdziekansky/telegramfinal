from telegram import Update
from utils.translations import get_text
from handlers.menu_handler import get_user_language
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from config import SUBSCRIPTION_EXPIRED_MESSAGE
from database.supabase_client import check_active_subscription
from utils.openai_client import analyze_document, analyze_image

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    language = get_user_language(context, user_id)    """Obsługa przesłanych dokumentów"""
    user_id = update.effective_user.id
    
    # Sprawdź, czy użytkownik ma aktywną subskrypcję
    if not check_active_subscription(user_id):
        await update.message.reply_text(SUBSCRIPTION_EXPIRED_MESSAGE)
        return
    
    document = update.message.document
    file_name = document.file_name
    
    # Sprawdź rozmiar pliku (limit 25MB)
    if document.file_size > 25 * 1024 * 1024:
        await update.message.reply_text(get_text("file_too_large", language))
        return
    
    # Pobierz plik
    message = await update.message.reply_text(get_text("analyzing_file", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj plik
    analysis = analyze_document(file_bytes, file_name)
    
    # Wyślij analizę do użytkownika
    await message.edit_text(
        f"*{get_text('file_analysis', language)}:* {file_name}\n\n{analysis}",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsługa przesłanych zdjęć"""
    user_id = update.effective_user.id
    
    # Sprawdź, czy użytkownik ma aktywną subskrypcję
    if not check_active_subscription(user_id):
        await update.message.reply_text(SUBSCRIPTION_EXPIRED_MESSAGE)
        return
    
    # Wybierz zdjęcie o najwyższej rozdzielczości
    photo = update.message.photo[-1]
    
    # Pobierz zdjęcie
    message = await update.message.reply_text(get_text("analyzing_photo", language))
    
    # Wyślij informację o aktywności bota
    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Analizuj zdjęcie
    analysis = analyze_image(file_bytes, f"photo_{photo.file_unique_id}.jpg")
    
    # Wyślij analizę do użytkownika
    await message.edit_text(
        f"*{get_text('photo_analysis', language)}:*\n\n{analysis}",
        parse_mode=ParseMode.MARKDOWN
    )