import os
import asyncio
from collections import deque

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8539661882  # your Telegram ID

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ================== STATE ==================

waiting_user = None
active_chats = {}

authorized_users = {OWNER_ID}
revoked_users = set()

# reports (temporary, in-memory)
reports = {}                  # user_id -> count
reported_this_chat = set()    # reporter ids

# blocks (temporary, in-memory)
blocks = {}                   # user_id -> set(blocked_user_ids)

# message pacing
message_queues = {}           # user_id -> deque
queue_tasks = {}              # user_id -> asyncio.Task
queue_warned = set()

QUEUE_DELAY = 1.0
QUEUE_LIMIT = 10

# ================== KEYBOARDS ==================

keyboard = ReplyKeyboardMarkup(
    [["🔄 Next", "❌ Stop"],
     ["🚨 Report", "🚫 Block"]],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    [["🚫 Revoke", "✅ Allow"]],
    resize_keyboard=True
)

# ================== HELPERS ==================

def is_owner(uid: int) -> bool:
    return uid == OWNER_ID

def is_active(uid: int) -> bool:
    return uid in authorized_users and uid not in revoked_users

# ================== QUEUE WORKER ==================

async def process_queue(uid: int, context: ContextTypes.DEFAULT_TYPE):
    while message_queues.get(uid):
        msg = message_queues[uid].popleft()

        if uid not in active_chats:
            break

        await context.bot.send_message(active_chats[uid], msg)
        await asyncio.sleep(QUEUE_DELAY)

    message_queues.pop(uid, None)
    queue_tasks.pop(uid, None)
    queue_warned.discard(uid)

# ================== COMMANDS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_active(uid):
        await update.message.reply_text(
            "🔒 Invite-only anonymous chatbot.\n\n"
            "Use:\n"
            "/join <code>"
        )
        return

    await update.message.reply_text(
        "Welcome.\nTap 🔄 Next to find a stranger.",
        reply_markup=keyboard
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid in revoked_users:
        await update.message.reply_text("🚫 Access revoked.")
        return

    if context.args and context.args[0] == "test123":
        authorized_users.add(uid)
        await update.message.reply_text(
            "✅ Access granted.",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text("❌ Invalid invite code.")

async def reports_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not reports:
        await update.message.reply_text("No reports yet.")
        return

    text = "🚨 Reported users:\n\n"
    for uid, count in sorted(reports.items(), key=lambda x: -x[1]):
        text += f"{uid} — {count} reports\n"

    await update.message.reply_text(text, reply_markup=admin_keyboard)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        return

    uid = int(context.args[0])
    count = reports.get(uid, 0)

    await update.message.reply_text(
        f"User: {uid}\nReports: {count}",
        reply_markup=admin_keyboard
    )

async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /revoke <user_id>")
        return

    target = int(context.args[0])
    revoked_users.add(target)
    authorized_users.discard(target)

    if target in active_chats:
        partner = active_chats.pop(target)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Partner disconnected.")

    await update.message.reply_text(f"User {target} revoked.")

# ================== CHAT FLOW ==================

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_user
    uid = update.effective_user.id

    if not is_active(uid):
        return

    if uid in active_chats:
        partner = active_chats.pop(uid)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Partner left.")

    if (
        waiting_user
        and waiting_user != uid
        and waiting_user not in blocks.get(uid, set())
        and uid not in blocks.get(waiting_user, set())
    ):
        partner = waiting_user
        waiting_user = None
        active_chats[uid] = partner
        active_chats[partner] = uid

        reported_this_chat.discard(uid)
        reported_this_chat.discard(partner)

        await context.bot.send_message(partner, "🔗 Connected.", reply_markup=keyboard)
        await update.message.reply_text("🔗 Connected.", reply_markup=keyboard)
    else:
        waiting_user = uid
        await update.message.reply_text("⏳ Searching...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid in active_chats:
        partner = active_chats.pop(uid)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "⚠️ Partner disconnected.")

    await update.message.reply_text("Chat ended.")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in active_chats or uid in reported_this_chat:
        return

    target = active_chats[uid]
    reports[target] = reports.get(target, 0) + 1
    reported_this_chat.add(uid)

    await update.message.reply_text("🚨 Report submitted. Chat ended.")
    await stop(update, context)

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in active_chats:
        return

    target = active_chats[uid]

    blocks.setdefault(uid, set()).add(target)
    blocks.setdefault(target, set()).add(uid)

    await update.message.reply_text(
        "🚫 User blocked. You won’t be matched again."
    )
    await stop(update, context)

# ================== MESSAGE RELAY ==================

async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    if not is_active(uid):
        return

    if text == "🔄 Next":
        await next_chat(update, context)
        return

    if text == "❌ Stop":
        await stop(update, context)
        return

    if text == "🚨 Report":
        await report(update, context)
        return

    if text == "🚫 Block":
        await block(update, context)
        return

    if uid not in active_chats:
        await update.message.reply_text("Tap 🔄 Next.")
        return

    if uid not in message_queues:
        message_queues[uid] = deque()

    if len(message_queues[uid]) >= QUEUE_LIMIT:
        if uid not in queue_warned:
            queue_warned.add(uid)
            await update.message.reply_text("⏳ Slow down. Messages queued.")
        return

    message_queues[uid].append(text)

    if uid not in queue_tasks:
        queue_tasks[uid] = asyncio.create_task(
            process_queue(uid, context)
        )

# ================== START APP ==================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("reports", reports_cmd))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("revoke", revoke))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()

