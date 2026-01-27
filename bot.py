
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


TOKEN = os.getenv("BOT_TOKEN")


waiting_user = None
active_chats = {}

keyboard = ReplyKeyboardMarkup(
    [["🔄 Next", "❌ Stop"]],
    resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome. Tap 🔄 Next to find a stranger.\nTap ❌ Stop to end chat.",
        reply_markup=keyboard
    )


async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_user
    user_id = update.effective_user.id

    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "Stranger left the chat.")

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
        await context.bot.send_message(partner, "Stranger left the chat.")

    await update.message.reply_text("Chat stopped.")


async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

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
    if user_id in active_chats:
        partner = active_chats[user_id]
        await context.bot.send_message(partner, update.message.text)
    else:
        await update.message.reply_text("Use /next to find a stranger.")


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("next", next_chat))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

app.run_polling()

