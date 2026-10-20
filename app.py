import os
import threading
import time
from flask import Flask
import telebot
from telebot import types
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN")
MONGODB_URI = os.environ.get("MONGODB_URI")

if not TOKEN:
    raise ValueError("BOT_TOKEN ENVIRONMENT VARIABLE IS NOT SET")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI ENVIRONMENT VARIABLE IS NOT SET")

ADMIN_ID = 6795305850
YT_CHANNEL_URL = "https://youtube.com/@R2FSUNILYT"  # Aapka YouTube Channel Link

bot = telebot.TeleBot(TOKEN)


# ============================================================
# MONGODB DATABASE
# ============================================================

try:
    mongo_client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
    )

    mongo_client.admin.command("ping")

    db = mongo_client["r2f_free_bot"]

    keys_collection = db["keys_table"]
    free_claims_collection = db["free_claims"]

    keys_collection.create_index(
        [("license_key", ASCENDING)],
        unique=True,
        name="unique_license_key",
    )

    keys_collection.create_index(
        [("duration", ASCENDING), ("status", ASCENDING)]
    )

    free_claims_collection.create_index(
        [("user_id", ASCENDING)],
        unique=True,
        name="unique_free_claim_user",
    )

    print("MONGODB CONNECTED SUCCESSFULLY!")

except Exception as e:
    raise RuntimeError(f"MONGODB CONNECTION FAILED: {e}")


# ============================================================
# START COMMAND (ONLY 1 BUTTON)
# ============================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id

    # Check if user already claimed their free key
    claimed = free_claims_collection.find_one({"user_id": user_id})
    if claimed:
        bot.send_message(
            message.chat.id,
            f"❌ *Aap apni free 5-hour key pehle hi claim kar chuke hain!*\n\n"
            f"🔑 *Aapki Key:* `{claimed.get('license_key')}`",
            parse_mode="Markdown"
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎁 GET FREE KEY", callback_data="start_timer")
    )

    bot.send_message(
        message.chat.id,
        "💎 *WELCOME TO R2F FREE KEY BOT* ✅\n\n"
        "🎁 *FREE 5-HOUR KEY GIVEAWAY* ✨\n\n"
        f"1️⃣ Pehle yahan click karke hamara YouTube channel subscribe karein: \n👉 {YT_CHANNEL_URL}\n\n"
        "2️⃣ Subscribe karne ke baad niche diye gaye **'GET FREE KEY'** button par click karein (25 seconds mein verification complete hogi).",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ============================================================
# TIMER & VERIFICATION CALLBACK (25 SECONDS)
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data == "start_timer")
def handle_start_timer(call):
    user_id = call.from_user.id

    claimed = free_claims_collection.find_one({"user_id": user_id})
    if claimed:
        bot.answer_callback_query(call.id, "❌ Aap pehle hi free key claim kar chuke hain!", show_alert=True)
        return

    bot.answer_callback_query(call.id, "⏳ Verifying... Please wait 25 seconds.", show_alert=False)

    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        bot.edit_message_text(
            "⏳ *VERIFICATION IN PROGRESS...*\n\n"
            "Kripya 25 seconds wait karein, subscription check ho rahi hai...",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown"
        )
    except Exception:
        pass

    def delayed_verification():
        time.sleep(25)

        if free_claims_collection.find_one({"user_id": user_id}):
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("✅ VERIFIED & GET FREE KEY", callback_data="claim_free_key")
        )

        try:
            bot.edit_message_text(
                "✅ *VERIFICATION SUCCESSFUL!* ✅\n\n"
                "Ab niche diye gaye button par click karke apni **Free 5-Hour Key** claim karein:",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception:
            pass

    threading.Thread(target=delayed_verification, daemon=True).start()


# ============================================================
# CLAIM FREE KEY CALLBACK
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data == "claim_free_key")
def handle_claim_free_key(call):
    user_id = call.from_user.id

    claimed = free_claims_collection.find_one({"user_id": user_id})
    if claimed:
        bot.answer_callback_query(call.id, "❌ Aap pehle hi free key claim kar chuke hain!", show_alert=True)
        return

    key_row = keys_collection.find_one_and_update(
        {
            "duration": "5 Hour",
            "status": "unused"
        },
        {
            "$set": {
                "status": "used",
                "assigned_to": user_id
            }
        },
        return_document=True
    )

    if not key_row:
        bot.answer_callback_query(call.id, "❌ Out of stock! Filhal 5 Hour ki free key available nahi hai.", show_alert=True)
        return

    try:
        free_claims_collection.insert_one({
            "user_id": user_id,
            "key_id": key_row["id"] if "id" in key_row else 0,
            "license_key": key_row["license_key"],
            "claimed_at": time.time()
        })
    except Exception:
        pass

    bot.answer_callback_query(call.id, "🎉 Success! Aapko free key mil gayi hai.", show_alert=True)

    try:
        bot.edit_message_text(
            f"🎉 *CONGRATULATIONS! YEH RAHI AAPKI FREE 5-HOUR KEY:* ✅\n\n"
            f"🔑 `{key_row['license_key']}`\n\n"
            f"⚠️ *Note:* Is key ko sambhal kar rakhein, ye dobara nahi milegi.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            f"🎉 *CONGRATULATIONS! YEH RAHI AAPKI FREE 5-HOUR KEY:* ✅\n\n"
            f"🔑 `{key_row['license_key']}`",
            parse_mode="Markdown"
        )


# ============================================================
# ADMIN COMMAND TO ADD 5-HR KEYS: /addkey <key>
# ============================================================

@bot.message_handler(commands=["addkey"])
def handle_add_key(message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ *Sahi format use karein:*\n`/addkey YOUR_LICENSE_KEY`", parse_mode="Markdown")
        return

    license_key = parts[1].strip()

    try:
        keys_collection.insert_one({
            "duration": "5 Hour",
            "license_key": license_key,
            "status": "unused",
            "assigned_to": None
        })
        bot.reply_to(message, f"✅ *5-Hour Key Successfully Added:*\n`{license_key}`", parse_mode="Markdown")
    except DuplicateKeyError:
        bot.reply_to(message, "❌ *Duplicate Error:* Yeh key pehle se database mein mojood hai.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")


# ============================================================
# FLASK SERVER (FOR RENDER DEPLOYMENT)
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "FREE KEY BOT IS ACTIVE AND RUNNING!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ============================================================
# START BOT
# ============================================================

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    try:
        bot.remove_webhook()
        bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"WEBHOOK CLEANUP ERROR: {e}")

    print("FREE KEY BOT IS RUNNING...")

    bot.infinity_polling(timeout=60, long_polling_timeout=60)
