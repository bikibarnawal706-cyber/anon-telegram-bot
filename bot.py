from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8536390960:AAE9znir2HIel3V3dqkvktTIxm2eGz9raBg"

waiting_user = None
active_chats = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome. Use /next to find a stranger.\nUse /stop to end chat."
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
        await context.bot.send_message(partner, "You are now connected to a stranger.")
        await update.message.reply_text("You are now connected to a stranger.")
    else:
        waiting_user = user_id
        await update.message.reply_text("Searching for a stranger...")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_chats:
        partner = active_chats.pop(user_id)
        active_chats.pop(partner, None)
        await context.bot.send_message(partner, "Stranger left the chat.")

    await update.message.reply_text("Chat stopped.")


async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

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
