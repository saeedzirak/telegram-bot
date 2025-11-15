# bot.py
import logging
import csv
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------- تنظیمات (از متغیر محیطی خوانده می‌شوند) -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")        # مقدار را در Railway وارد می‌کنیم
CHANNEL_ID = os.environ.get("CHANNEL_ID")      # مثال: @YourChannelUsername یا -1001234567890
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))  # آیدی عددی ادمین

if not BOT_TOKEN or not CHANNEL_ID or ADMIN_CHAT_ID == 0:
    logger.error("لطفاً متغیرهای محیطی BOT_TOKEN، CHANNEL_ID و ADMIN_CHAT_ID را تنظیم کنید.")
    raise SystemExit("Missing environment variables")

CSV_FILE = "submissions.csv"

CHECK_MEMBERSHIP, WAIT_CODE, WAIT_NAME, CONFIRM = range(4)

def save_submission(data: dict):
    header = ["user_id", "username", "code", "full_name"]
    exists = False
    try:
        with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
            exists = True
    except FileNotFoundError:
        exists = False

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "user_id": data.get("user_id"),
            "username": data.get("username") or "",
            "code": data.get("code"),
            "full_name": data.get("full_name"),
        })

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("رفتن به کانال و عضویت", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
        [InlineKeyboardButton("بررسی عضویت", callback_data="check_member")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "سلام! برای شرکت در مسابقه ابتدا لطفاً عضو کانال ما شو و سپس دکمهٔ «بررسی عضویت» را بزن.",
        reply_markup=reply_markup
    )
    return CHECK_MEMBERSHIP

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

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
    code = update.message.text.strip()
    context.user_data["code"] = code
    await update.message.reply_text("کد دریافت شد. لطفاً نام و نام‌خانوادگی خود را وارد کنید:")
    return WAIT_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text.strip()
    context.user_data["full_name"] = full_name

    code = context.user_data.get("code", "")
    username = update.effective_user.username or ""
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

    data = {
        "user_id": user.id,
        "username": user.username,
        "code": context.user_data.get("code", ""),
        "full_name": context.user_data.get("full_name", "")
    }

    try:
        save_submission(data)
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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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
    logger.info("Bot is starting (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
