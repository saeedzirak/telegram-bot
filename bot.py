# bot.py
import logging
import csv
import os
import sys
import re
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تنظیم لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ----------------- تنظیمات -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not all([BOT_TOKEN, CHANNEL_ID, ADMIN_CHAT_ID]):
    logger.error("لطفاً متغیرهای محیطی BOT_TOKEN، CHANNEL_ID و ADMIN_CHAT_ID را تنظیم کنید.")
    sys.exit(1)

try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
except ValueError:
    logger.error("ADMIN_CHAT_ID باید یک عدد باشد")
    sys.exit(1)

# فایل‌ها
CSV_FILE = "submissions.csv"
USED_CODES_FILE = "used_codes.json"
VALID_CODES_FILE = "valid_codes.txt"

# حالت‌های مکالمه
CHECK_MEMBERSHIP, WAIT_CODE, WAIT_NAME, CONFIRM = range(4)

# ----------------- مدیریت کدها -----------------
def load_valid_codes():
    """بارگذاری کدهای معتبر از فایل"""
    try:
        with open(VALID_CODES_FILE, "r", encoding="utf-8") as f:
            codes = {line.strip().upper() for line in f if line.strip()}
            if not codes:
                logger.error("❌ فایل valid_codes.txt خالی است!")
                return set()
            logger.info(f"✅ {len(codes)} کد معتبر از فایل بارگذاری شد")
            return codes
    except FileNotFoundError:
        logger.error("❌ فایل valid_codes.txt پیدا نشد!")
        return set()

def load_used_codes():
    """بارگذاری کدهای استفاده شده"""
    try:
        with open(USED_CODES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_used_codes(used_codes):
    """ذخیره کدهای استفاده شده"""
    with open(USED_CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(used_codes), f)

def is_code_already_used_by_other_user(code: str, current_user_id: int) -> bool:
    """بررسی می‌کند که آیا کد توسط کاربر دیگری استفاده شده است"""
    try:
        if not os.path.exists(CSV_FILE):
            return False
            
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row["code"] and row["code"].upper() == code.upper() and 
                    row["user_id"] and int(row["user_id"]) != current_user_id):
                    return True
        return False
    except Exception as e:
        logger.error(f"خطا در بررسی استفاده کد توسط دیگران: {e}")
        return False

def is_valid_code_format(code: str) -> bool:
    """بررسی فرمت کد"""
    if len(code) != 6:
        return False
    
    pattern = r'^[A-Z0-9]{6}$'
    return bool(re.match(pattern, code))

def is_valid_code(code: str, user_id: int) -> tuple[bool, str]:
    """بررسی کامل کد و بازگرداندن پیام خطا"""
    code_upper = code.upper()
    
    # بررسی فرمت
    if not is_valid_code_format(code_upper):
        return False, f"❌ فرمت کد نامعتبر!\nکد باید ۶ کاراکتر و فقط شامل حروف بزرگ و اعداد انگلیسی باشد.\nمثال: ABC123"
    
    # بررسی وجود در لیست معتبر
    valid_codes = load_valid_codes()
    if not valid_codes:
        return False, "❌ سیستم کدها آماده نیست. لطفاً با ادمین تماس بگیرید."
    
    if code_upper not in valid_codes:
        return False, "❌ کد نامعتبر! این کد در سیستم وجود ندارد."
    
    # بررسی استفاده نشدن توسط کاربران دیگر
    if is_code_already_used_by_other_user(code_upper, user_id):
        return False, "❌ این کد قبلاً توسط کاربر دیگری استفاده شده است!"
    
    # بررسی استفاده نشدن در سیستم
    used_codes = load_used_codes()
    if code_upper in used_codes:
        return False, "❌ این کد قبلاً استفاده شده است!"
    
    return True, "✅ کد معتبر است"

def mark_code_as_used(code: str):
    """علامت گذاری کد به عنوان استفاده شده"""
    used_codes = load_used_codes()
    used_codes.add(code.upper())
    save_used_codes(used_codes)

# ----------------- مدیریت کاربران -----------------
def has_user_submitted(user_id: int) -> bool:
    """بررسی می‌کند که کاربر قبلاً ثبت نام کرده یا نه"""
    try:
        if not os.path.exists(CSV_FILE):
            return False
            
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["user_id"] and int(row["user_id"]) == user_id:
                    return True
        return False
    except Exception as e:
        logger.error(f"خطا در بررسی ثبت نام کاربر: {e}")
        return False

def save_submission(data: dict):
    """ذخیره اطلاعات در فایل CSV"""
    header = ["user_id", "username", "code", "full_name"]
    file_exists = os.path.isfile(CSV_FILE)
    
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "user_id": data.get("user_id"),
            "username": data.get("username") or "",
            "code": data.get("code", ""),
            "full_name": data.get("full_name", ""),
        })

def get_participant_count():
    """تعداد کل شرکت‌کنندگان"""
    try:
        if not os.path.exists(CSV_FILE):
            return 0
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            return sum(1 for row in reader) - 1
    except Exception as e:
        logger.error(f"خطا در شمارش شرکت‌کنندگان: {e}")
        return 0

def get_all_participants():
    """لیست تمام کاربران شرکت‌کننده"""
    participants = []
    try:
        if not os.path.exists(CSV_FILE):
            return participants
            
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["user_id"]:
                    participants.append(int(row["user_id"]))
    except Exception as e:
        logger.error(f"خطا در دریافت لیست کاربران: {e}")
    
    return participants

# ----------------- دستورات ربات -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if has_user_submitted(user.id):
        await update.message.reply_text(
            "❌ شما قبلاً در مسابقه شرکت کرده‌اید!\n"
            "هر نفر فقط می‌تواند یک بار شرکت کند."
        )
        return ConversationHandler.END
    
    valid_codes = load_valid_codes()
    if not valid_codes:
        await update.message.reply_text(
            "❌ سیستم در حال حاضر در دسترس نیست.\n"
            "لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید."
        )
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("رفتن به کانال و عضویت", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
        [InlineKeyboardButton("بررسی عضویت", callback_data="check_member")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "سلام! برای شرکت در مسابقه ابتدا لطفاً عضو کانال ما شو و سپس دکمهٔ «بررسی عضویت» را بزن.دوست من راز مطالب ویژه و شانس برنده شدن مسابقه های هفتگی تو پیج اینستاگراممونه!سری بزنین:@usbacc_club",
        reply_markup=reply_markup
    )
    return CHECK_MEMBERSHIP

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if has_user_submitted(user.id):
        await query.edit_message_text(
            "❌ شما قبلاً در مسابقه شرکت کرده‌اید!\n"
            "هر نفر فقط می‌تواند یک بار شرکت کند."
        )
        return ConversationHandler.END

    try:
        chat = CHANNEL_ID
        member = await context.bot.get_chat_member(chat_id=chat, user_id=user.id)
        status = member.status
    except Exception as e:
        logger.exception("خطا در بررسی عضویت")
        await query.edit_message_text("خطا در برقراری ارتباط با کانال. لطفاً مطمئن شوید ربات عضو/ادمین کانال است.")
        return ConversationHandler.END

    if status in ("creator", "administrator", "member"):
        await query.edit_message_text("عضویت تأیید شد ✅\nلطفاً کدی که روی جعبهٔ پذیرایی هست را وارد کن:")
        return WAIT_CODE
    else:
        keyboard = [
            [InlineKeyboardButton("رفتن به کانال و عضویت", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
            [InlineKeyboardButton("بررسی دوباره", callback_data="check_member")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("شما هنوز عضو کانال نیستید. لطفاً عضو شوید و سپس «بررسی دوباره» را بزنید.", reply_markup=reply_markup)
        return CHECK_MEMBERSHIP

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if has_user_submitted(user.id):
        await update.message.reply_text("❌ شما قبلاً در مسابقه شرکت کرده‌اید!")
        return ConversationHandler.END
        
    code = update.message.text.strip()
    
    # اعتبارسنجی کامل کد با در نظر گرفتن کاربر فعلی
    is_valid, message = is_valid_code(code, user.id)
    if not is_valid:
        await update.message.reply_text(message + "\n\nلطفاً کد صحیح را وارد کنید:")
        return WAIT_CODE
    
    context.user_data["code"] = code.upper()
    await update.message.reply_text("✅ کد معتبر! لطفاً نام و نام‌خانوادگی خود را وارد کنید:")
    return WAIT_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if has_user_submitted(user.id):
        await update.message.reply_text("❌ شما قبلاً در مسابقه شرکت کرده‌اید!")
        return ConversationHandler.END
        
    full_name = update.message.text.strip()
    
    if len(full_name) < 2 or len(full_name) > 50:
        await update.message.reply_text("❌ نام باید بین ۲ تا ۵۰ کاراکتر باشد. لطفاً دوباره وارد کنید:")
        return WAIT_NAME
        
    context.user_data["full_name"] = full_name

    code = context.user_data.get("code", "")
    username = user.username or ""
    msg = f"لطفاً اطلاعات را بررسی کن:\n\nکد: {code}\nنام و نام‌خانوادگی: {full_name}\nنام کاربری تلگرام: @{username}\n\nاگر صحیح است «شرکت در مسابقه» را بزن."
    keyboard = [
        [InlineKeyboardButton("شرکت در مسابقه ✅", callback_data="submit_entry")]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM

async def submit_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if has_user_submitted(user.id):
        await query.edit_message_text("❌ شما قبلاً در مسابقه شرکت کرده‌اید!")
        return ConversationHandler.END

    data = {
        "user_id": user.id,
        "username": user.username,
        "code": context.user_data.get("code", ""),
        "full_name": context.user_data.get("full_name", "")
    }

    try:
        save_submission(data)
        mark_code_as_used(data["code"])
    except Exception as e:
        logger.exception("خطا در ذخیره‌سازی")
        await query.edit_message_text("خطا در ذخیره اطلاعات. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    admin_text = (
        f"🔔 ورودی جدید مسابقه:\n\n"
        f"آیدی کاربر: {data['user_id']}\n"
        f"نام کاربری: @{data['username']}\n"
        f"کد: {data['code']}\n"
        f"نام و نام‌خانوادگی: {data['full_name']}\n"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
    except Exception as e:
        logger.exception("خطا در ارسال به ادمین")

    await query.edit_message_text("ثبت شد ✅\nممنون که شرکت کردی!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("فرایند کنسل شد.")
    return ConversationHandler.END

# ----------------- دستورات ادمین -----------------
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده آمار (فقط ادمین)"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    
    try:
        participant_count = get_participant_count()
        used_codes_count = len(load_used_codes())
        valid_codes_count = len(load_valid_codes())
        
        stats_text = (
            f"📊 آمار مسابقه:\n\n"
            f"👥 تعداد شرکت‌کنندگان: {participant_count}\n"
            f"🔢 کدهای استفاده شده: {used_codes_count}\n"
            f"🏷️ کدهای موجود: {valid_codes_count}\n"
            f"📝 کدهای باقی‌مانده: {valid_codes_count - used_codes_count}"
        )
        
        await update.message.reply_text(stats_text)
        
    except Exception as e:
        logger.exception("خطا در دریافت آمار")
        await update.message.reply_text("خطا در دریافت آمار")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به همه شرکت‌کنندگان (فقط ادمین)"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢使用方法:\n"
            "/broadcast <پیام>\n\n"
            "مثال:\n"
            "/broadcast سلام به همه شرکت‌کنندگان عزیز!"
        )
        return
    
    message_text = ' '.join(context.args)
    participants_count = get_participant_count()
    
    if participants_count == 0:
        await update.message.reply_text("❌ هیچ کاربری برای ارسال پیام وجود ندارد.")
        return
    
    # ذخیره پیام در context برای استفاده در callback
    context.user_data["broadcast_message"] = message_text
    
    keyboard = [
        [
            InlineKeyboardButton("✅ بله، ارسال کن", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ لغو", callback_data="cancel_broadcast")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📢 آیا مطمئنی می‌خوای این پیام رو برای {participants_count} کاربر ارسال کنی؟\n\n"
        f"پیام: {message_text}",
        reply_markup=reply_markup
    )

async def broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید و ارسال پیام دسته‌جمعی"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_broadcast":
        await query.edit_message_text("❌ ارسال پیام لغو شد.")
        return
    
    message_text = context.user_data.get("broadcast_message", "")
    
    if not message_text:
        await query.edit_message_text("❌ پیامی برای ارسال پیدا نشد.")
        return
    
    await query.edit_message_text("🔄 در حال ارسال پیام به کاربران...")
    
    success_count = 0
    fail_count = 0
    participants = get_all_participants()
    
    for user_id in participants:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 پیام از مدیریت:\n\n{message_text}\n\n—\nربات مسابقه"
            )
            success_count += 1
        except Exception as e:
            logger.warning(f"خطا در ارسال به کاربر {user_id}: {e}")
            fail_count += 1
        
        # تأخیر برای جلوگیری از محدودیت تلگرام
        await asyncio.sleep(0.2)
    
    # گزارش به ادمین
    report_text = (
        f"📊 گزارش ارسال دسته‌جمعی:\n\n"
        f"✅ ارسال موفق: {success_count} کاربر\n"
        f"❌ ارسال ناموفق: {fail_count} کاربر\n"
        f"📝 کل کاربران: {len(participants)}"
    )
    
    await query.edit_message_text(report_text)

def main():
    logger.info("🚀 شروع ربات...")
    
    valid_codes = load_valid_codes()
    if not valid_codes:
        logger.error("❌ هیچ کد معتبری بارگذاری نشد! ربات متوقف می‌شود.")
        return
    
    logger.info(f"✅ {len(valid_codes)} کد معتبر بارگذاری شد")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handler برای کاربران عادی
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHECK_MEMBERSHIP: [
                CallbackQueryHandler(button_callback, pattern="^check_member$")
            ],
            WAIT_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)
            ],
            WAIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)
            ],
            CONFIRM: [
                CallbackQueryHandler(submit_entry_callback, pattern="^submit_entry$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    
    # دستورات ادمین
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CallbackQueryHandler(broadcast_confirmation, pattern="^(confirm_broadcast|cancel_broadcast)$"))
    
    logger.info("✅ ربات راه‌اندازی شد")
    app.run_polling()

if __name__ == "__main__":
    main()