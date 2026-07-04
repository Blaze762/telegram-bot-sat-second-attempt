#!/usr/bin/env python3
"""
=============================================================
  SAT Mock Test Checker Bot
  Author: Custom Build
  Platform: Render.com (Long Polling)
  Library: python-telegram-bot v20+
=============================================================

FEATURES:
  - Multi-language support (English + Uzbek)
  - Channel membership verification before any action
  - Students can submit answers and get instant feedback
  - Students can view their submission history
  - Admin can add new tests with answer keys
  - Admin can view statistics
  - All data stored persistently in data.json
  - Unlimited retries per student

HOW TO RUN:
  pip install python-telegram-bot
  python bot.py
=============================================================
"""

import os
import json
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# =============================================================
# LOGGING SETUP
# =============================================================
# Configure logging so we can see what's happening in the terminal
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
# Reduce noise from httpx (the HTTP library used internally)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Create our own logger for this bot
logger = logging.getLogger(__name__)

# =============================================================
# CONFIGURATION
# =============================================================

# Bot token — reads from environment variable, falls back to hardcoded default
BOT_TOKEN = os.getenv("BOT_TOKEN", "8849469661:AAHCLs5ncz4P-SpyHt_BSPRgZ5r-9vI1gG8")

# Channel 1: public username (students must follow this)
CHANNEL_1_USERNAME = "@sat_ielts_dars"

# Channel 2: private channel ID (students must follow this too)
CHANNEL_2_ID = int(os.getenv("CHANNEL_2_ID", "-1004471248965"))

# Channel 2 invite link (shown to users who haven't joined yet)
CHANNEL_2_INVITE = "https://t.me/+B3p0JKHEn6ljNTli"

# Admin user ID — only this Telegram user can use admin commands
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "1715205655"))

# Path to our persistent JSON data file
DATA_FILE = "data.json"

# =============================================================
# CONVERSATION STATES
# =============================================================
# These integers represent the "steps" in a multi-step conversation.
# ConversationHandler uses them to know which function to call next.

# States for /submit conversation
SUBMIT_WAITING_FOR_ANSWERS = 1

# States for /addtest conversation
ADDTEST_WAITING_FOR_NAME    = 10
ADDTEST_WAITING_FOR_ANSWERS = 11

# =============================================================
# MULTILINGUAL TEXTS
# =============================================================
# All user-facing strings are stored here.
# "en" = English, "uz" = Uzbek (O'zbek)
# Admin messages also read from here using the admin's chosen language.

TEXTS = {
    "en": {
        # --- Language Selection ---
        "choose_language": (
            "👋 Welcome to *SAT Mock Test Checker Bot*!\n\n"
            "Please choose your language:"
        ),
        "language_set": "✅ Language set to *English*. Welcome!",

        # --- Channel Check ---
        "not_member": (
            "❌ *You must follow both channels first!*\n\n"
            "Please join the channels below and then send /start again:\n\n"
            "📢 Channel 1: {channel1}\n"
            "📢 Channel 2: {channel2}\n\n"
            "After joining, send /start again."
        ),

        # --- Start / Main Menu ---
        "welcome": (
            "✅ Welcome, *{name}*!\n\n"
            "📝 *Active Test:* `{test_name}`\n\n"
            "Use the commands below:\n"
            "• /submit — Submit your answers\n"
            "• /history — View your past results\n"
            "• /help — Show all commands\n"
            "• /language — Change language"
        ),
        "no_active_test": (
            "⚠️ There is no active test right now.\n"
            "Please check back later!"
        ),

        # --- Submit Conversation ---
        "submit_prompt": (
            "📋 *Test:* `{test_name}`\n\n"
            "Please paste your answers below.\n"
            "Format: one answer per line, like this:\n\n"
            "`1 A`\n`2 B`\n`3 15`\n`4 D`\n\n"
            "Send /cancel to abort."
        ),
        "submit_processing": "⏳ Checking your answers...",
        "submit_result": (
            "📊 *Your Result for* `{test_name}`\n"
            "🗓 Date: {date}\n\n"
            "✅ *Score: {score}/{total}*\n\n"
            "{wrong_section}"
        ),
        "submit_perfect": "🎉 *Perfect score! Excellent work!*",
        "wrong_answers_header": "❌ *Wrong Answers:*\n",
        "wrong_answer_line": "  Q{num}: Your answer `{user_ans}` → Correct: `{correct_ans}`\n",
        "unanswered_line": "  Q{num}: *Not answered* → Correct: `{correct_ans}`\n",
        "submit_parse_error": (
            "⚠️ *Could not read your answers.*\n\n"
            "Please use this format:\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Each line must start with the question number, then the answer.\n"
            "Send /cancel to abort or try again."
        ),
        "submit_cancelled": "❌ Submission cancelled.",

        # --- History ---
        "history_header": "📜 *Your Submission History:*\n\n",
        "history_entry": (
            "📝 *{test_name}*\n"
            "   🗓 Date: {date}\n"
            "   ✅ Score: {score}/{total}\n\n"
        ),
        "history_empty": "📭 You have no submissions yet.\nUse /submit to take a test!",

        # --- Help ---
        "help_text": (
            "📖 *SAT Mock Test Checker Bot — Help*\n\n"
            "*Student Commands:*\n"
            "• /start — Show active test & menu\n"
            "• /submit — Submit your answers for grading\n"
            "• /history — View your past results\n"
            "• /language — Change your language\n"
            "• /help — Show this help message\n"
            "• /cancel — Cancel current action\n\n"
            "*Answer Format:*\n"
            "One answer per line:\n"
            "`1 A`\n`2 B`\n`3 15`\n`4 D`\n\n"
            "Letters are case-insensitive (a = A).\n"
            "You may retry unlimited times!"
        ),

        # --- Language change ---
        "language_menu": "🌐 Choose your language:",
        "language_already_set": "✅ Your language is already set to *English*.",

        # --- Admin: Add Test ---
        "admin_only": "🚫 This command is for admins only.",
        "addtest_usage": (
            "⚠️ Usage: `/addtest TEST_NAME`\n\n"
            "Example: `/addtest SAT-Mock-06`"
        ),
        "addtest_name_set": (
            "✅ Test name set: *{test_name}*\n\n"
            "Now paste the answer key.\n"
            "Format — one per line:\n\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Send /cancel to abort."
        ),
        "addtest_saved": (
            "✅ *Test saved successfully!*\n\n"
            "📝 Test Name: `{test_name}`\n"
            "🔢 Total Questions: {total}\n\n"
            "This is now the *active test*."
        ),
        "addtest_parse_error": (
            "⚠️ *Could not parse the answer key.*\n\n"
            "Use this format:\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Try again or send /cancel."
        ),
        "addtest_cancelled": "❌ Add test cancelled.",

        # --- Admin: Stats ---
        "stats_header": (
            "📊 *Bot Statistics*\n\n"
            "📝 *Active Test:* `{test_name}`\n"
            "👥 *Unique Students (current test):* {unique_students}\n"
            "📨 *Total Submissions (current test):* {total_submissions}\n"
            "👤 *Total Registered Users:* {total_users}\n"
        ),
        "stats_no_test": "⚠️ No active test. Use /addtest to create one.",

        # --- General ---
        "cancelled": "❌ Action cancelled.",
        "error": "⚠️ Something went wrong. Please try again.",
    },

    "uz": {
        # --- Language Selection ---
        "choose_language": (
            "👋 *SAT Mock Test Checker Bot*ga xush kelibsiz!\n\n"
            "Iltimos, tilingizni tanlang:"
        ),
        "language_set": "✅ Til *O'zbek* tiliga o'rnatildi. Xush kelibsiz!",

        # --- Channel Check ---
        "not_member": (
            "❌ *Avval ikkala kanalga ham obuna bo'lishingiz kerak!*\n\n"
            "Quyidagi kanallarga qo'shiling va keyin /start ni qayta yuboring:\n\n"
            "📢 Kanal 1: {channel1}\n"
            "📢 Kanal 2: {channel2}\n\n"
            "Qo'shilgandan so'ng, /start ni yuboring."
        ),

        # --- Start / Main Menu ---
        "welcome": (
            "✅ Xush kelibsiz, *{name}*!\n\n"
            "📝 *Faol test:* `{test_name}`\n\n"
            "Quyidagi buyruqlardan foydalaning:\n"
            "• /submit — Javoblaringizni yuboring\n"
            "• /history — O'tgan natijalaringizni ko'ring\n"
            "• /help — Barcha buyruqlarni ko'ring\n"
            "• /language — Tilni o'zgartiring"
        ),
        "no_active_test": (
            "⚠️ Hozirda faol test mavjud emas.\n"
            "Keyinroq tekshiring!"
        ),

        # --- Submit Conversation ---
        "submit_prompt": (
            "📋 *Test:* `{test_name}`\n\n"
            "Iltimos, javoblaringizni pastga joylashtiring.\n"
            "Format: har bir qator uchun bitta javob:\n\n"
            "`1 A`\n`2 B`\n`3 15`\n`4 D`\n\n"
            "Bekor qilish uchun /cancel yuboring."
        ),
        "submit_processing": "⏳ Javoblaringiz tekshirilmoqda...",
        "submit_result": (
            "📊 *`{test_name}` uchun natijangiz*\n"
            "🗓 Sana: {date}\n\n"
            "✅ *Ball: {score}/{total}*\n\n"
            "{wrong_section}"
        ),
        "submit_perfect": "🎉 *To'liq ball! Ajoyib natija!*",
        "wrong_answers_header": "❌ *Noto'g'ri javoblar:*\n",
        "wrong_answer_line": "  {num}-savol: Sizning javobingiz `{user_ans}` → To'g'ri: `{correct_ans}`\n",
        "unanswered_line": "  {num}-savol: *Javob berilmagan* → To'g'ri: `{correct_ans}`\n",
        "submit_parse_error": (
            "⚠️ *Javoblaringizni o'qib bo'lmadi.*\n\n"
            "Iltimos, quyidagi formatdan foydalaning:\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Har bir qator savol raqami bilan boshlanishi kerak.\n"
            "Bekor qilish uchun /cancel yoki qaytadan urining."
        ),
        "submit_cancelled": "❌ Yuborish bekor qilindi.",

        # --- History ---
        "history_header": "📜 *Sizning yuborish tarixi:*\n\n",
        "history_entry": (
            "📝 *{test_name}*\n"
            "   🗓 Sana: {date}\n"
            "   ✅ Ball: {score}/{total}\n\n"
        ),
        "history_empty": "📭 Sizda hali yuborishlar yo'q.\nTest topshirish uchun /submit dan foydalaning!",

        # --- Help ---
        "help_text": (
            "📖 *SAT Mock Test Checker Bot — Yordam*\n\n"
            "*Talaba buyruqlari:*\n"
            "• /start — Faol testni va menyuni ko'rsatish\n"
            "• /submit — Javoblaringizni baholash uchun yuboring\n"
            "• /history — O'tgan natijalaringizni ko'ring\n"
            "• /language — Tilingizni o'zgartiring\n"
            "• /help — Ushbu yordam xabarini ko'rsatish\n"
            "• /cancel — Joriy amalni bekor qilish\n\n"
            "*Javob formati:*\n"
            "Har bir qatorda bitta javob:\n"
            "`1 A`\n`2 B`\n`3 15`\n`4 D`\n\n"
            "Harflar katta-kichikligiga qaramasdan qabul qilinadi (a = A).\n"
            "Cheksiz urinishlar mumkin!"
        ),

        # --- Language change ---
        "language_menu": "🌐 Tilingizni tanlang:",
        "language_already_set": "✅ Tilingiz allaqachon *O'zbek* tiliga o'rnatilgan.",

        # --- Admin: Add Test ---
        "admin_only": "🚫 Bu buyruq faqat adminlar uchun.",
        "addtest_usage": (
            "⚠️ Ishlatish: `/addtest TEST_NOMI`\n\n"
            "Misol: `/addtest SAT-Mock-06`"
        ),
        "addtest_name_set": (
            "✅ Test nomi belgilandi: *{test_name}*\n\n"
            "Endi javoblar kalitini joylashtiring.\n"
            "Format — har bir qatorda bitta:\n\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Bekor qilish uchun /cancel yuboring."
        ),
        "addtest_saved": (
            "✅ *Test muvaffaqiyatli saqlandi!*\n\n"
            "📝 Test nomi: `{test_name}`\n"
            "🔢 Jami savollar: {total}\n\n"
            "Bu endi *faol test* hisoblanadi."
        ),
        "addtest_parse_error": (
            "⚠️ *Javoblar kalitini o'qib bo'lmadi.*\n\n"
            "Quyidagi formatdan foydalaning:\n"
            "`1 A`\n`2 B`\n`3 15`\n\n"
            "Qayta urining yoki /cancel yuboring."
        ),
        "addtest_cancelled": "❌ Test qo'shish bekor qilindi.",

        # --- Admin: Stats ---
        "stats_header": (
            "📊 *Bot Statistikasi*\n\n"
            "📝 *Faol test:* `{test_name}`\n"
            "👥 *Noyob talabalar (joriy test):* {unique_students}\n"
            "📨 *Jami yuborishlar (joriy test):* {total_submissions}\n"
            "👤 *Jami ro'yxatdan o'tgan foydalanuvchilar:* {total_users}\n"
        ),
        "stats_no_test": "⚠️ Faol test yo'q. Test yaratish uchun /addtest dan foydalaning.",

        # --- General ---
        "cancelled": "❌ Amal bekor qilindi.",
        "error": "⚠️ Nimadir noto'g'ri ketdi. Iltimos, qayta urinib ko'ring.",
    },
}

# =============================================================
# DATA MANAGEMENT
# =============================================================
# We store all data in a single JSON file for simplicity.
# The structure is:
# {
#   "active_test": "SAT-Mock-05",
#   "tests": {
#       "SAT-Mock-05": {
#           "answers": { "1": "A", "2": "B", ... }
#       }
#   },
#   "users": {
#       "123456789": {
#           "language": "en",
#           "history": [
#               {
#                   "test_name": "SAT-Mock-05",
#                   "date": "2025-01-15 14:32",
#                   "score": 67,
#                   "total": 80
#               }
#           ]
#       }
#   }
# }


def load_data() -> dict:
    """
    Load data from data.json.
    If the file doesn't exist or is corrupted, return a fresh default structure.
    """
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load %s: %s. Starting fresh.", DATA_FILE, e)

    # Default empty structure
    return {
        "active_test": None,  # Name of the currently active test
        "tests": {},          # Dictionary of all test data (name → answers)
        "users": {},          # Dictionary of all user data (user_id → profile)
    }


def save_data(data: dict) -> None:
    """
    Save the entire data dictionary to data.json.
    Uses indentation for readability.
    """
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error("Failed to save %s: %s", DATA_FILE, e)


def get_user_language(data: dict, user_id: int) -> str:
    """
    Get the stored language for a user.
    Returns 'en' as the default if user hasn't chosen yet.
    """
    uid = str(user_id)
    return data.get("users", {}).get(uid, {}).get("language", "en")


def set_user_language(data: dict, user_id: int, lang: str) -> None:
    """
    Set and persist the language preference for a user.
    Creates the user record if it doesn't exist.
    """
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"language": lang, "history": []}
    else:
        data["users"][uid]["language"] = lang
    save_data(data)


def ensure_user_exists(data: dict, user_id: int) -> None:
    """
    Make sure a user record exists in the data dictionary.
    If not, create a default one (language = 'en').
    """
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"language": "en", "history": []}
        save_data(data)


def t(data: dict, user_id: int, key: str) -> str:
    """
    Shortcut function to get a translated text string.
    Looks up the user's language and returns the matching text.

    Args:
        data: The full loaded data dictionary
        user_id: The Telegram user ID
        key: The text key from the TEXTS dictionary

    Returns:
        The translated string for the user's language.
        Falls back to English if key doesn't exist in chosen language.
    """
    lang = get_user_language(data, user_id)
    # Fall back to English if the key is missing in the chosen language
    return TEXTS.get(lang, TEXTS["en"]).get(key, TEXTS["en"].get(key, "⚠️ Missing text"))


# =============================================================
# CHANNEL MEMBERSHIP CHECK
# =============================================================

async def check_membership(bot, user_id: int) -> bool:
    """
    Check if a user is a member of BOTH required channels.

    Uses Telegram's getChatMember API.
    Valid membership statuses: 'member', 'administrator', 'creator'
    Invalid statuses: 'left', 'kicked', 'restricted'

    Returns True if the user is in both channels, False otherwise.
    """
    # These statuses mean the user IS in the channel
    valid_statuses = {"member", "administrator", "creator"}

    # Check Channel 1 (by username)
    try:
        member1 = await bot.get_chat_member(
            chat_id=CHANNEL_1_USERNAME,
            user_id=user_id
        )
        in_channel1 = member1.status in valid_statuses
    except TelegramError as e:
        logger.warning("Could not check Channel 1 membership for user %s: %s", user_id, e)
        # If we can't check (e.g., bot isn't admin), assume they are a member
        # to avoid blocking users unnecessarily. Adjust this if needed.
        in_channel1 = True

    # Check Channel 2 (by numeric ID)
    try:
        member2 = await bot.get_chat_member(
            chat_id=CHANNEL_2_ID,
            user_id=user_id
        )
        in_channel2 = member2.status in valid_statuses
    except TelegramError as e:
        logger.warning("Could not check Channel 2 membership for user %s: %s", user_id, e)
        in_channel2 = True

    return in_channel1 and in_channel2


async def send_not_member_message(update: Update, data: dict, user_id: int) -> None:
    """
    Send the "please join channels" message to a user who isn't subscribed yet.
    Shows links to both channels.
    """
    message_text = t(data, user_id, "not_member").format(
        channel1=CHANNEL_1_USERNAME,
        channel2=CHANNEL_2_INVITE,
    )

    # Build inline keyboard with channel links
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel 1", url=f"https://t.me/{CHANNEL_1_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("📢 Channel 2", url=CHANNEL_2_INVITE)],
    ])

    await update.effective_message.reply_text(
        message_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# =============================================================
# ANSWER PARSING
# =============================================================

def parse_answers(raw_text: str) -> dict | None:
    """
    Parse a multi-line answer string into a dictionary.
    Expects lines like:
        1 A
        2 B
        3 15
        4 D

    Returns:
        A dict like {"1": "A", "2": "B", "3": "15", "4": "D"}
        Returns None if parsing fails (bad format or empty input).
    """
    answers = {}
    lines = raw_text.strip().splitlines()

    if not lines:
        return None  # Empty input

    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip blank lines

        # Split on whitespace; we expect exactly 2 parts: number and answer
        parts = line.split(None, 1)  # Split on any whitespace, max 2 parts
        if len(parts) != 2:
            logger.debug("Could not parse answer line: '%s'", line)
            return None  # Malformed line

        q_num, answer = parts[0].strip(), parts[1].strip()

        # The first part must be a valid question number (integer)
        if not q_num.isdigit():
            logger.debug("Question number is not a digit: '%s'", q_num)
            return None

        answers[q_num] = answer  # Store as strings; comparison done later

    if not answers:
        return None  # Nothing was parsed successfully

    return answers


def compare_answers(correct: dict, student: dict) -> tuple[int, list]:
    """
    Compare student answers against the correct answer key.

    Comparison rules:
    - Both answers are stripped of whitespace
    - Letters are compared case-insensitively (A == a)
    - Numbers are compared as stripped strings ("15" == "15")

    Args:
        correct: Dict of {question_number: correct_answer}
        student: Dict of {question_number: student_answer}

    Returns:
        A tuple of:
          - score (int): Number of correct answers
          - wrong_list (list): List of dicts with wrong question details
            Each dict: {"num": str, "user_ans": str, "correct_ans": str, "unanswered": bool}
    """
    score = 0
    wrong_list = []

    # Iterate over all questions in the answer key
    for q_num, correct_ans in correct.items():
        student_ans = student.get(q_num, None)

        if student_ans is None:
            # Student did not answer this question
            wrong_list.append({
                "num": q_num,
                "user_ans": "—",
                "correct_ans": correct_ans,
                "unanswered": True,
            })
        else:
            # Compare case-insensitively and stripped
            if student_ans.strip().upper() == correct_ans.strip().upper():
                score += 1
            else:
                wrong_list.append({
                    "num": q_num,
                    "user_ans": student_ans,
                    "correct_ans": correct_ans,
                    "unanswered": False,
                })

    # Sort wrong answers by question number for neat display
    wrong_list.sort(key=lambda x: int(x["num"]) if x["num"].isdigit() else 0)

    return score, wrong_list


# =============================================================
# LANGUAGE SELECTION HANDLERS
# =============================================================

async def show_language_selection(update: Update, user_id: int) -> None:
    """
    Display the language selection inline keyboard.
    Used both on first /start and when /language is called.
    """
    data = load_data()

    # Determine greeting text
    # If the user has a language set, use it; otherwise default to English
    lang = get_user_language(data, user_id)
    text = TEXTS.get(lang, TEXTS["en"])["choose_language"]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])

    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the inline button presses for language selection (lang_en / lang_uz).
    Saves the chosen language and confirms to the user.
    """
    query = update.callback_query
    await query.answer()  # Acknowledge the button press (removes loading indicator)

    user_id = query.from_user.id
    chosen_lang = query.data  # "lang_en" or "lang_uz"

    data = load_data()
    ensure_user_exists(data, user_id)

    # Map the callback data to a language code
    if chosen_lang == "lang_uz":
        lang_code = "uz"
    else:
        lang_code = "en"

    # Save the language preference
    set_user_language(data, user_id, lang_code)
    logger.info("User %s selected language: %s", user_id, lang_code)

    # Confirm language selection
    confirmation_text = TEXTS[lang_code]["language_set"]
    await query.edit_message_text(confirmation_text, parse_mode="Markdown")

    # Immediately show the main start menu after language selection
    # Re-load data since we just saved
    data = load_data()

    # Check membership before showing main menu
    is_member = await check_membership(context.bot, user_id)
    if not is_member:
        await send_not_member_message(update, data, user_id)
        return

    # Show the main welcome message
    await show_main_menu(update, context, data, user_id, query.from_user.first_name)


# =============================================================
# START COMMAND
# =============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start command handler.

    Flow:
    1. Check if user has chosen a language. If not → show language selection keyboard.
    2. Check channel membership. If not member → show join channels message.
    3. Show the active test and main menu.
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Student"

    logger.info("User %s (%s) sent /start", user_id, user_name)

    data = load_data()
    ensure_user_exists(data, user_id)

    # Check if user has selected a language yet
    uid = str(user_id)
    user_record = data["users"].get(uid, {})

    # If 'language' key is missing → first time user → show language selection
    if "language" not in data["users"].get(uid, {}):
        await show_language_selection(update, user_id)
        return

    # Membership check
    is_member = await check_membership(context.bot, user_id)
    if not is_member:
        await send_not_member_message(update, data, user_id)
        return

    # Everything is good → show main menu
    await show_main_menu(update, context, data, user_id, user_name)


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict,
    user_id: int,
    user_name: str,
) -> None:
    """
    Display the main welcome/menu message showing the active test.
    """
    active_test = data.get("active_test")

    if not active_test:
        # No test has been created yet
        message_text = t(data, user_id, "no_active_test")
    else:
        message_text = t(data, user_id, "welcome").format(
            name=user_name,
            test_name=active_test,
        )

    await update.effective_message.reply_text(message_text, parse_mode="Markdown")


# =============================================================
# LANGUAGE COMMAND
# =============================================================

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /language command — lets the user change their language at any time.
    """
    user_id = update.effective_user.id
    logger.info("User %s used /language", user_id)

    data = load_data()
    ensure_user_exists(data, user_id)

    # Show the language selection keyboard again
    await show_language_selection(update, user_id)


# =============================================================
# HELP COMMAND
# =============================================================

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /help command — show list of all available commands.
    """
    user_id = update.effective_user.id
    logger.info("User %s used /help", user_id)

    data = load_data()
    ensure_user_exists(data, user_id)

    await update.message.reply_text(
        t(data, user_id, "help_text"),
        parse_mode="Markdown",
    )


# =============================================================
# HISTORY COMMAND
# =============================================================

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /history command — show the user's past test submissions.

    Displays: test name, date, and score for each submission.
    Requires channel membership.
    """
    user_id = update.effective_user.id
    logger.info("User %s used /history", user_id)

    data = load_data()
    ensure_user_exists(data, user_id)

    # Membership check
    is_member = await check_membership(context.bot, user_id)
    if not is_member:
        await send_not_member_message(update, data, user_id)
        return

    # Get user's submission history
    uid = str(user_id)
    history = data["users"].get(uid, {}).get("history", [])

    if not history:
        await update.message.reply_text(
            t(data, user_id, "history_empty"),
            parse_mode="Markdown",
        )
        return

    # Build history message
    # Show most recent entries first (reverse chronological order)
    msg = t(data, user_id, "history_header")
    for entry in reversed(history):
        msg += t(data, user_id, "history_entry").format(
            test_name=entry.get("test_name", "Unknown"),
            date=entry.get("date", "Unknown"),
            score=entry.get("score", 0),
            total=entry.get("total", 0),
        )

    await update.message.reply_text(msg, parse_mode="Markdown")


# =============================================================
# SUBMIT CONVERSATION
# =============================================================
# This is a 2-step conversation:
#   Step 1: User sends /submit → bot asks for answers
#   Step 2: User pastes answers → bot checks and returns results

async def cmd_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    STEP 1 of the submit conversation.
    Entry point: user sends /submit
    - Check membership
    - Check that an active test exists
    - Ask user to paste their answers
    """
    user_id = update.effective_user.id
    logger.info("User %s started /submit", user_id)

    data = load_data()
    ensure_user_exists(data, user_id)

    # Membership check
    is_member = await check_membership(context.bot, user_id)
    if not is_member:
        await send_not_member_message(update, data, user_id)
        return ConversationHandler.END  # End conversation

    # Check that there's an active test
    active_test = data.get("active_test")
    if not active_test:
        await update.message.reply_text(
            t(data, user_id, "no_active_test"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END  # End conversation

    # Store the active test name in context for the next step
    context.user_data["submit_test_name"] = active_test

    # Prompt the user to paste their answers
    await update.message.reply_text(
        t(data, user_id, "submit_prompt").format(test_name=active_test),
        parse_mode="Markdown",
    )

    # Move to the next state: waiting for the user's answers
    return SUBMIT_WAITING_FOR_ANSWERS


async def receive_student_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    STEP 2 of the submit conversation.
    User has pasted their answers → parse, compare, and return results.
    """
    user_id = update.effective_user.id
    raw_text = update.message.text

    logger.info("User %s submitted answers (length: %d chars)", user_id, len(raw_text))

    data = load_data()

    # Show "processing" indicator
    processing_msg = await update.message.reply_text(
        t(data, user_id, "submit_processing"),
    )

    # Parse the student's answers
    student_answers = parse_answers(raw_text)

    if student_answers is None:
        # Could not parse → show error and stay in the same state so they can retry
        await processing_msg.delete()
        await update.message.reply_text(
            t(data, user_id, "submit_parse_error"),
            parse_mode="Markdown",
        )
        return SUBMIT_WAITING_FOR_ANSWERS  # Stay in same state (let them try again)

    # Get the test name stored during step 1
    test_name = context.user_data.get("submit_test_name")

    if not test_name or test_name not in data.get("tests", {}):
        # The test was deleted or changed between steps — edge case
        await processing_msg.delete()
        await update.message.reply_text(
            t(data, user_id, "no_active_test"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Get the correct answers for this test
    correct_answers = data["tests"][test_name]["answers"]
    total_questions = len(correct_answers)

    # Compare student answers against the correct key
    score, wrong_list = compare_answers(correct_answers, student_answers)

    # Build the wrong answers section of the result message
    if wrong_list:
        lang = get_user_language(data, user_id)
        wrong_section = TEXTS[lang]["wrong_answers_header"]

        for item in wrong_list:
            if item["unanswered"]:
                wrong_section += TEXTS[lang]["unanswered_line"].format(
                    num=item["num"],
                    correct_ans=item["correct_ans"],
                )
            else:
                wrong_section += TEXTS[lang]["wrong_answer_line"].format(
                    num=item["num"],
                    user_ans=item["user_ans"],
                    correct_ans=item["correct_ans"],
                )
    else:
        # All correct!
        lang = get_user_language(data, user_id)
        wrong_section = TEXTS[lang]["submit_perfect"]

    # Format the current date/time
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build the full result message
    result_text = t(data, user_id, "submit_result").format(
        test_name=test_name,
        date=now_str,
        score=score,
        total=total_questions,
        wrong_section=wrong_section,
    )

    # Save this submission to the user's history
    uid = str(user_id)
    history_entry = {
        "test_name": test_name,
        "date": now_str,
        "score": score,
        "total": total_questions,
    }

    # Append to user's history list
    if uid not in data["users"]:
        data["users"][uid] = {"language": "en", "history": []}
    data["users"][uid].setdefault("history", []).append(history_entry)
    save_data(data)

    logger.info(
        "User %s scored %d/%d on test '%s'",
        user_id, score, total_questions, test_name
    )

    # Delete the "processing" message and send results
    await processing_msg.delete()
    await update.message.reply_text(result_text, parse_mode="Markdown")

    # End the conversation
    return ConversationHandler.END


async def cmd_cancel_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the /submit conversation when user sends /cancel.
    """
    user_id = update.effective_user.id
    data = load_data()

    logger.info("User %s cancelled /submit", user_id)

    await update.message.reply_text(
        t(data, user_id, "submit_cancelled"),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


# =============================================================
# ADMIN: ADD TEST CONVERSATION
# =============================================================
# This is a 2-step admin conversation:
#   Step 1: Admin sends /addtest TEST_NAME → bot confirms name, asks for answer key
#   Step 2: Admin pastes answer key → bot saves the test as active

async def cmd_addtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    STEP 1 of the addtest conversation.
    Entry point: admin sends /addtest TEST_NAME
    - Verify admin identity
    - Parse the test name from the command arguments
    - Ask admin to paste the answer key
    """
    user_id = update.effective_user.id

    data = load_data()
    ensure_user_exists(data, user_id)

    # Check admin privileges
    if user_id != ADMIN_USER_ID:
        logger.warning("Non-admin user %s tried to use /addtest", user_id)
        await update.message.reply_text(
            t(data, user_id, "admin_only"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Get the test name from command arguments
    # context.args contains the words after the command
    if not context.args:
        await update.message.reply_text(
            t(data, user_id, "addtest_usage"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Join all args in case test name has spaces (e.g., /addtest SAT Mock 05)
    test_name = " ".join(context.args).strip()

    if not test_name:
        await update.message.reply_text(
            t(data, user_id, "addtest_usage"),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    logger.info("Admin %s is adding test: '%s'", user_id, test_name)

    # Store the test name in context for step 2
    context.user_data["new_test_name"] = test_name

    # Confirm and ask for the answer key
    await update.message.reply_text(
        t(data, user_id, "addtest_name_set").format(test_name=test_name),
        parse_mode="Markdown",
    )

    return ADDTEST_WAITING_FOR_ANSWERS


async def receive_answer_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    STEP 2 of the addtest conversation.
    Admin has pasted the answer key → parse and save as the new active test.
    """
    user_id = update.effective_user.id
    raw_text = update.message.text

    data = load_data()

    # Parse the answer key using the same parser as student answers
    answers = parse_answers(raw_text)

    if answers is None:
        await update.message.reply_text(
            t(data, user_id, "addtest_parse_error"),
            parse_mode="Markdown",
        )
        return ADDTEST_WAITING_FOR_ANSWERS  # Stay in same state, let admin retry

    # Get the test name stored in step 1
    test_name = context.user_data.get("new_test_name", "Unknown Test")
    total_questions = len(answers)

    # Save the new test to data
    # This preserves old tests in "tests" dict; only changes "active_test"
    if "tests" not in data:
        data["tests"] = {}

    data["tests"][test_name] = {
        "answers": answers,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data["active_test"] = test_name  # Set as the currently active test
    save_data(data)

    logger.info(
        "Admin %s saved test '%s' with %d questions. Set as active.",
        user_id, test_name, total_questions
    )

    await update.message.reply_text(
        t(data, user_id, "addtest_saved").format(
            test_name=test_name,
            total=total_questions,
        ),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


async def cmd_cancel_addtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the /addtest conversation.
    """
    user_id = update.effective_user.id
    data = load_data()

    logger.info("Admin %s cancelled /addtest", user_id)

    await update.message.reply_text(
        t(data, user_id, "addtest_cancelled"),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


# =============================================================
# ADMIN: STATS COMMAND
# =============================================================

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /stats command — show statistics about the current active test.

    Only accessible by the admin.
    Shows:
    - Current active test name
    - Number of unique students who submitted the current test
    - Total number of submissions for the current test
    - Total registered users
    """
    user_id = update.effective_user.id
    data = load_data()
    ensure_user_exists(data, user_id)

    # Admin check
    if user_id != ADMIN_USER_ID:
        logger.warning("Non-admin user %s tried to use /stats", user_id)
        await update.message.reply_text(
            t(data, user_id, "admin_only"),
            parse_mode="Markdown",
        )
        return

    active_test = data.get("active_test")

    if not active_test:
        await update.message.reply_text(
            t(data, user_id, "stats_no_test"),
            parse_mode="Markdown",
        )
        return

    # Count unique students and total submissions for the current active test
    unique_students = set()
    total_submissions = 0

    for uid, user_record in data.get("users", {}).items():
        history = user_record.get("history", [])
        for entry in history:
            if entry.get("test_name") == active_test:
                unique_students.add(uid)
                total_submissions += 1

    total_users = len(data.get("users", {}))

    await update.message.reply_text(
        t(data, user_id, "stats_header").format(
            test_name=active_test,
            unique_students=len(unique_students),
            total_submissions=total_submissions,
            total_users=total_users,
        ),
        parse_mode="Markdown",
    )

    logger.info("Admin %s viewed stats for test '%s'", user_id, active_test)


# =============================================================
# GENERIC CANCEL COMMAND
# =============================================================

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Generic /cancel command — cancels any ongoing operation.
    Can be used outside of conversations too.
    """
    user_id = update.effective_user.id
    data = load_data()

    await update.message.reply_text(
        t(data, user_id, "cancelled"),
        parse_mode="Markdown",
    )

    return ConversationHandler.END


# =============================================================
# ERROR HANDLER
# =============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler — catches all unhandled exceptions.
    Logs the error and optionally notifies the admin.
    """
    logger.error("Exception while handling update:", exc_info=context.error)

    # Try to notify the admin about the error
    try:
        error_msg = (
            f"⚠️ *Bot Error*\n\n"
            f"`{type(context.error).__name__}: {str(context.error)}`"
        )
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=error_msg,
            parse_mode="Markdown",
        )
    except Exception:
        pass  # If we can't notify admin, just continue silently


# =============================================================
# MAIN FUNCTION — BOT SETUP AND LAUNCH
# =============================================================

def main() -> None:
    """
    Main entry point.
    - Builds the Application
    - Registers all handlers (commands, conversations, callbacks)
    - Starts long polling
    """
    logger.info("=" * 60)
    logger.info("  SAT Mock Test Checker Bot — Starting Up")
    logger.info("=" * 60)
    logger.info("Admin User ID  : %s", ADMIN_USER_ID)
    logger.info("Channel 1      : %s", CHANNEL_1_USERNAME)
    logger.info("Channel 2 ID   : %s", CHANNEL_2_ID)
    logger.info("Data file      : %s", DATA_FILE)
    logger.info("=" * 60)

    # Build the Application using the bot token
    # ApplicationBuilder is the modern way to create the application in v20+
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # ----------------------------------------------------------
    # CONVERSATION HANDLER: /submit
    # ----------------------------------------------------------
    # This handles the 2-step answer submission process:
    # Step 1 (entry): /submit → ask for answers
    # Step 2: user sends answers → grade and respond
    submit_conversation = ConversationHandler(
        entry_points=[CommandHandler("submit", cmd_submit)],
        states={
            SUBMIT_WAITING_FOR_ANSWERS: [
                # Accept any text that is NOT a command
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_student_answers),
            ],
        },
        fallbacks=[
            # /cancel exits the conversation at any point
            CommandHandler("cancel", cmd_cancel_submit),
            # If user sends any command other than /cancel, also end
            MessageHandler(filters.COMMAND, cmd_cancel_submit),
        ],
        # Allow conversation to be started fresh if user runs /submit again
        allow_reentry=True,
    )

    # ----------------------------------------------------------
    # CONVERSATION HANDLER: /addtest (Admin only)
    # ----------------------------------------------------------
    # Step 1 (entry): /addtest TEST_NAME → confirm name, ask for answer key
    # Step 2: admin sends answer key → save test
    addtest_conversation = ConversationHandler(
        entry_points=[CommandHandler("addtest", cmd_addtest)],
        states={
            ADDTEST_WAITING_FOR_ANSWERS: [
                # Accept any text that is NOT a command
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer_key),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel_addtest),
            MessageHandler(filters.COMMAND, cmd_cancel_addtest),
        ],
        allow_reentry=True,
    )

    # ----------------------------------------------------------
    # REGISTER ALL HANDLERS
    # ----------------------------------------------------------

    # Conversation handlers (must be added BEFORE standalone command handlers
    # to avoid interference)
    application.add_handler(submit_conversation)
    application.add_handler(addtest_conversation)

    # Standard command handlers
    application.add_handler(CommandHandler("start",    cmd_start))
    application.add_handler(CommandHandler("help",     cmd_help))
    application.add_handler(CommandHandler("history",  cmd_history))
    application.add_handler(CommandHandler("language", cmd_language))
    application.add_handler(CommandHandler("stats",    cmd_stats))
    application.add_handler(CommandHandler("cancel",   cmd_cancel))

    # Callback query handler for inline keyboard buttons (language selection)
    # Matches any callback data starting with "lang_"
    application.add_handler(
        CallbackQueryHandler(handle_language_callback, pattern="^lang_")
    )

    # Global error handler — catches all unhandled exceptions
    application.add_error_handler(error_handler)

    # ----------------------------------------------------------
    # START POLLING
    # ----------------------------------------------------------
    logger.info("Bot is now running with long polling...")
    logger.info("Press Ctrl+C to stop.")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,  # Receive all update types
        drop_pending_updates=True,         # Ignore messages sent while bot was offline
    )


# ----------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------
if __name__ == "__main__":
    main()
