# bot_full_with_buttons.py
import sqlite3
import json
import logging

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# --- SOZLAMALAR ---
BOT_TOKEN = ""
ADMINS = []
CHANNEL_FILE = "channels.json"
USERS_FILE = "users.json"
DB_FILE = "movies.db"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- JSON bilan ishlash ---
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_channels():
    return load_json(CHANNEL_FILE)

def save_channels(channels):
    save_json(CHANNEL_FILE, channels)

def load_users():
    return load_json(USERS_FILE)

def save_users(users):
    save_json(USERS_FILE, users)

def add_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

# --- DB funksiyalar ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_id TEXT,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_movie(code, file_id, caption=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO movies (code, file_id, caption) VALUES (?, ?, ?)", (code, file_id, caption))
    conn.commit()
    conn.close()

def get_movie(code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file_id, caption FROM movies WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    return row if row else None

# --- Kanal obuna tekshirish ---
async def is_subscribed(user_id, context: ContextTypes.DEFAULT_TYPE):
    channels = load_channels()
    for channel in channels:
        if channel.startswith("http"):
            continue
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logger.warning("Kanal tekshirishda xato: %s (channel=%s)", e, channel)
            return False
    return True

# --- Bot komandalar ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id)
    await update.message.reply_text("Salom! 🎬 Kod yuboring va men kino chiqarib beraman.")

async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Sizga ruxsat yo‘q!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Kino fayliga reply qilib /save CODE yozing.")
        return
    code = context.args[0] if context.args else None
    if not code:
        await update.message.reply_text("❌ Kod yozmadingiz. Masalan: /save M1")
        return

    rm = update.message.reply_to_message
    file_id, caption = None, rm.caption or ""

    if rm.video:
        file_id = rm.video.file_id
    elif rm.document:
        file_id = rm.document.file_id
    elif rm.photo:
        file_id = rm.photo[-1].file_id

    if file_id:
        add_movie(code, file_id, caption)
        await update.message.reply_text(f"✅ Kino saqlandi! Kod: {code}")
    else:
        await update.message.reply_text("❌ Faqat video, rasm yoki faylga reply qiling.")

async def get_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()

    if not await is_subscribed(user_id, context):
        channels = load_channels()
        buttons = []
        for i, ch in enumerate(channels, start=1):
            url = f"https://t.me/{ch.replace('@','')}" if not ch.startswith("http") else ch
            buttons.append([InlineKeyboardButton(f"➕ Kanal-{i}", url=url)])
        buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data=f"check_{code}")])
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "❌ Avval quyidagi kanallarga a’zo bo‘ling, keyin qayta urinib ko‘ring 👇",
            reply_markup=markup
        )
        return

    movie = get_movie(code)
    if movie:
        file_id, caption = movie
        await update.message.reply_video(video=file_id, caption=caption or "")
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi.")

# --- Tekshirish tugmasi ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("check_"):
        code = data.replace("check_", "")
        user_id = query.from_user.id
        if await is_subscribed(user_id, context):
            movie = get_movie(code)
            if movie:
                file_id, caption = movie
                await query.message.reply_video(video=file_id, caption=caption or "")
            else:
                await query.message.reply_text("❌ Kod topilmadi.")
        else:
            await query.message.reply_text("❌ Hali hamma kanallarga a’zo bo‘lmadingiz.")

# --- Admin kanal qo‘shish / o‘chirish ---
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return
    if not context.args:
        await update.message.reply_text("❌ Kanal username yoki link yozing. Masalan: /addchannel @mychannel")
        return
    channel = context.args[0].strip()
    channels = load_channels()
    if channel not in channels:
        channels.append(channel)
        save_channels(channels)
        await update.message.reply_text(f"✅ {channel} qo‘shildi.")
    else:
        await update.message.reply_text("❌ Bu kanal allaqachon ro‘yxatda bor.")

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return
    if not context.args:
        await update.message.reply_text("❌ Kanal username yoki link yozing. Masalan: /delchannel @mychannel")
        return
    channel = context.args[0].strip()
    channels = load_channels()
    if channel in channels:
        channels.remove(channel)
        save_channels(channels)
        await update.message.reply_text(f"✅ {channel} o‘chirildi.")
    else:
        await update.message.reply_text("❌ Bu kanal ro‘yxatda yo‘q.")

# --- Reklama (broadcast) ---
async def reklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("❌ Hech qanday foydalanuvchi ro'yxatda yo'q.")
        return

    text = update.message.text or ""
    payload = text.partition(" ")[2].strip()
    if not payload and update.message.reply_to_message and update.message.reply_to_message.caption:
        payload = update.message.reply_to_message.caption

    lines = payload.splitlines() if payload else []
    caption_lines, buttons = [], []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            url, title = line.split("=", 1)
            url, title = url.strip(), title.strip()
            if url.startswith("@"):
                url = f"https://t.me/{url.lstrip('@')}"
            buttons.append([InlineKeyboardButton(title, url=url)])
        else:
            caption_lines.append(line)

    caption = "\n".join(caption_lines) if caption_lines else ""
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    reply_msg = update.message.reply_to_message

    sent_count, bad_users, total = 0, [], len(users)

    for uid in list(users):
        try:
            if reply_msg:
                if reply_msg.photo:
                    await context.bot.send_photo(uid, reply_msg.photo[-1].file_id, caption=caption, reply_markup=markup)
                elif reply_msg.video:
                    await context.bot.send_video(uid, reply_msg.video.file_id, caption=caption, reply_markup=markup)
                elif reply_msg.document:
                    await context.bot.send_document(uid, reply_msg.document.file_id, caption=caption, reply_markup=markup)
                else:
                    await context.bot.send_message(uid, text=caption, reply_markup=markup)
            else:
                await context.bot.send_message(uid, text=caption, reply_markup=markup)

            sent_count += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "forbidden" in err or "chat not found" in err:
                bad_users.append(uid)
            continue

    if bad_users:
        save_users([u for u in users if u not in bad_users])

    await update.message.reply_text(f"✅ Reklama yuborildi: {sent_count}/{total} foydalanuvchiga.")

# --- Main ---
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("save", save))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("delchannel", del_channel))
    app.add_handler(CommandHandler("reklama", reklama))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_by_code))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
