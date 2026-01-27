
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== TOKEN =====

TOKEN = os.getenv("BOT_TOKEN")

# ===== GLOBAL STATE =====

OWNER_ID = 8539661882  # <-- your Telegram user ID

waiting_user = None
active_chats = {}

authorized_users = {OWNER_ID}
revoked_users = set()

# ===== HELPERS =====

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_active(user_id: int) -> bool:
    return user_id in authorized_users and user_id not in revoked_users

# ===== KEYBOARD =====

keyboard = ReplyKeyboardMarkup(
    [["🔄 Next", "❌ Stop"]],
    resize_keyboard=True
)

# ===== COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in revoked_users:
        return

    if not is_active(user_id):
        await update.message.reply_text(
            "🔒 This chatbot is invite-only.\n\n"
            "If you have an invite code, send:\n"
            "/join <code>\n\n"
            "Example:\n"
            "/join TEST123"
        )
        return

    await update.message.reply_text(
        "Welcome.\nTap 🔄 Next to find a stranger.\nTap ❌ Stop to end chat.",
        reply_markup=keyboard
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in revoked_users:
        return

    if is_active(user_id):
        await update.message.reply_text("You already have access.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/join <invite_code>")
        return

    code = context.args[0]

    # TEMP MASTER INVITE
    if code == "TEST123":
        authorized_users.add(user_id)
        await update.message.reply_text(
            "✅ Access granted.\n\n"
            "Rules:\n"
            "• No personal info sharing\n"
            "• Leave anytime with ❌ Stop\n"
            "• Abuse = permanent removal\n\n"
            "Tap 🔄 Next to begin.",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("❌ Invalid invite code.")

async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller_id = update.effective_user.id

    if not is_owner(caller_id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/revoke <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    if target_id == OWNER_ID:
        await update.message.reply_text("❌ You cannot revoke yourself.")
        return

    authorized_users.discard(target_id)
    revoked_users.add(target_id)

    if target_id in active_chats:
        partner = active_chats.pop(target_id)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Stranger left the chat.")

    await update.message.reply_text(f"✅ User {target_id} revoked.")

async def allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller_id = update.effective_user.id

    if not is_owner(caller_id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/allow <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    revoked_users.discard(target_id)
    authorized_users.add(target_id)

    await update.message.reply_text(f"✅ User {target_id} allowed.")

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_user
    user_id = update.effective_user.id

    if not is_active(user_id):
        return

    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Stranger left the chat.")

    if waiting_user and waiting_user != user_id:
        partner = waiting_user
        waiting_user = None

        active_chats[user_id] = partner
        active_chats[partner] = user_id

        await context.bot.send_message(
            partner,
            "You are now connected to a stranger.",
            reply_markup=keyboard
        )

        await update.message.reply_text(
            "You are now connected to a stranger.",
            reply_markup=keyboard
        )
    else:
        waiting_user = user_id
        await update.message.reply_text(
            "Searching for a stranger...",
            reply_markup=keyboard
        )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Stranger left the chat.")

    await update.message.reply_text("Chat stopped.", reply_markup=keyboard)

async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_active(user_id):
        return

    if text == "🔄 Next":
        await next_chat(update, context)
        return

    if text == "❌ Stop":
        await stop(update, context)
        return

    if user_id in active_chats:
        partner = active_chats[user_id]
        await context.bot.send_message(partner, text)
    else:
        await update.message.reply_text(
            "Tap 🔄 Next to find a stranger.",
            reply_markup=keyboard
        )

# ===== APP SETUP =====

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("revoke", revoke))
app.add_handler(CommandHandler("allow", allow))
app.add_handler(CommandHandler("next", next_chat))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

app.run_polling()


