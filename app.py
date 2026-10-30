import os
import re
import threading
import time
import urllib.parse

from flask import Flask
import telebot
from telebot import types
from pymongo import MongoClient, ASCENDING, DESCENDING
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
UPI_ID = "8905094188@ybl"
UPI_NAME = "NEXA CYBER"
OWNER_USERNAME = "R2FSUNILYT"


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

    db = mongo_client["r2f_bot"]

    keys_collection = db["keys_table"]
    orders_collection = db["orders"]
    counters_collection = db["counters"]
    loaders_collection = db["loaders_table"]
    blocked_collection = db["blocked_users"]
    users_collection = db["users_table"]

    keys_collection.create_index(
        [("license_key", ASCENDING)],
        unique=True,
        name="unique_license_key",
    )

    keys_collection.create_index(
        [("platform", ASCENDING), ("duration", ASCENDING), ("status", ASCENDING)]
    )

    keys_collection.create_index(
        [("assigned_to", ASCENDING), ("status", ASCENDING)]
    )

    orders_collection.create_index(
        [("user_id", ASCENDING)]
    )

    loaders_collection.create_index(
        [("loader_key", ASCENDING)],
        unique=True,
        name="unique_loader_key",
    )

    blocked_collection.create_index(
        [("user_id", ASCENDING)],
        unique=True,
        name="unique_blocked_user",
    )

    users_collection.create_index(
        [("user_id", ASCENDING)],
        unique=True,
        name="unique_user_id",
    )

    print("MONGODB CONNECTED SUCCESSFULLY!")

except Exception as e:
    raise RuntimeError(f"MONGODB CONNECTION FAILED: {e}")


# ============================================================
# MONGODB AUTO INTEGER ID
# ============================================================

def get_next_id(sequence_name):
    result = counters_collection.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return result["seq"]


# ============================================================
# HELPER: PARSE DURATION TO SECONDS
# ============================================================

def parse_duration_seconds(duration_str):
    try:
        parts = duration_str.strip().lower().split()
        num = int(parts[0])
        unit = parts[1]
        if "hour" in unit:
            return num * 3600
        elif "day" in unit:
            return num * 86400
    except Exception:
        pass
    return 86400  # Default 1 day


# ============================================================
# USER STATE & TRACKING
# ============================================================

user_states = {}
admin_reply_map = {}
user_last_notif = {}  # Tracks last time user info header was sent to admin (24 hr limit)


# ============================================================
# HELPER: CHECK IF USER IS BLOCKED
# ============================================================

def is_blocked(user_id):
    if user_id == ADMIN_ID:
        return False
    return blocked_collection.find_one({"user_id": user_id}) is not None


# ============================================================
# HELPER: FORWARD MESSAGE TO ADMIN (ONCE PER 24 HR INFO HEADER)
# ============================================================

def forward_message_to_admin(message):
    try:
        user = message.from_user
        user_id = user.id
        if is_blocked(user_id):
            return

        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "username": user.username, "first_name": user.first_name}},
            upsert=True
        )

        current_time = time.time()

        if user_id not in user_last_notif or (current_time - user_last_notif[user_id]) > 86400:
            user_last_notif[user_id] = current_time
            username = f"@{user.username}" if user.username else "NO USERNAME"
            first_name = user.first_name if user.first_name else "USER"
            info_text = f"📩 *NEW MESSAGE FROM USER* ✅\n👤 NAME: {first_name}\n🆔 USER ID: `{user_id}`\n🔗 USERNAME: {username}"
            sent_info = bot.send_message(ADMIN_ID, info_text, parse_mode="Markdown")
            admin_reply_map[sent_info.message_id] = user_id

        sent_forward = bot.forward_message(ADMIN_ID, message.chat.id, message.id)
        admin_reply_map[sent_forward.message_id] = user_id
    except Exception as e:
        print(f"ERROR FORWARDING MESSAGE TO ADMIN: {e}")


# ============================================================
# BACKGROUND WORKER
# ============================================================

def send_timeout_failed_message(
    chat_id,
    user_id,
    order_id
):
    time.sleep(300)

    try:
        row = orders_collection.find_one(
            {"id": order_id},
            {"status": 1}
        )

        if row and row.get("status") in ["pending", "pending_admin"]:
            try:
                bot.send_message(
                    chat_id,
                    "⏳ *PAYMENT TIME EXPIRED!*\n"
                    "❌ *APPROVAL REQUEST CLOSED.*\n"
                    f"📩 *TRY AGAIN — CONTACT:* @{OWNER_USERNAME} ✅",
                    parse_mode="Markdown",
                    reply_markup=get_platform_keyboard(user_id),
                )
            except Exception:
                pass

    except Exception as e:
        print(f"TIMEOUT WORKER ERROR: {e}")


# ============================================================
# KEYBOARDS (REPLY KEYBOARDS)
# ============================================================

def get_platform_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("🤖 ANDROID"),
        types.KeyboardButton("🍏 iOS")
    )
    if user_id == ADMIN_ID:
        markup.add(
            types.KeyboardButton("👑 SUPER ADMIN"),
            types.KeyboardButton("📢 BROADCAST")
        )
    markup.add(
        types.KeyboardButton("💬 CONTACT SUPPORT")
    )
    return markup


def get_android_main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("🛒 PURCHASE KEY"),
        types.KeyboardButton("🔐 MY KEYS")
    )
    if user_id == ADMIN_ID:
        markup.add(
            types.KeyboardButton("🔑 GENERATE KEY")
        )
    markup.add(
        types.KeyboardButton("♻️ APK & SETUP"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_ios_main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("🛒 PURCHASE KEY (iOS)"),
        types.KeyboardButton("🔐 MY KEYS")
    )
    markup.add(
        types.KeyboardButton("📥 DOWNLOAD LINK"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_super_admin_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⚡ QR CODE MANAGER"),
        types.KeyboardButton("📂 ANDROID MANAGER")
    )
    markup.add(
        types.KeyboardButton("🍏 iOS MANAGER"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_android_manager_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("📂 ADD / UPDATE ANDROID APK"),
        types.KeyboardButton("📺 ADD / UPDATE ANDROID SETUP VIDEO"),
        types.KeyboardButton("🔑 ADD ANDROID KEYS (SINGLE & BULK)"),
        types.KeyboardButton("🪣 DELETE ANDROID KEYS"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_ios_manager_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("📥 ADD / UPDATE iOS DOWNLOAD LINK"),
        types.KeyboardButton("📺 ADD / UPDATE iOS SETUP VIDEO"),
        types.KeyboardButton("🔑 ADD iOS KEYS (SINGLE & BULK)"),
        types.KeyboardButton("🪣 DELETE iOS KEYS"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_qr_manager_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("🖼️ CHANGE UPI QR"),
        types.KeyboardButton("🎨 GENERATE CUSTOM QR"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_android_loader_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⚙️ VOLTAGE LOADER"),
        types.KeyboardButton("🚀 VIP LOADER"),
        types.KeyboardButton("💎 NICE X NEXA"),
        types.KeyboardButton("⚡ NICE X NEXA SERVER"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_ios_loader_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("🍏 WIN iOS"),
        types.KeyboardButton("👑 KING iOS"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_delete_options_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("🗑️ DELETE SINGLE KEY"),
        types.KeyboardButton("🗑️ DELETE ALL KEYS"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_android_durations_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⏱ 5 Hour"),
        types.KeyboardButton("⏱ 1 Day"),
        types.KeyboardButton("⏱ 2 Day"),
        types.KeyboardButton("⏱ 3 Day"),
        types.KeyboardButton("⏱ 7 Day"),
        types.KeyboardButton("⏱ 30 Day"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_ios_durations_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("⏱ 1 Day"),
        types.KeyboardButton("⏱ 7 Day"),
        types.KeyboardButton("⏱ 30 Day"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_key_method_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("➕ ADD SINGLE KEY"),
        types.KeyboardButton("📦 ADD BULK KEYS"),
        types.KeyboardButton("🔙 BACK")
    )
    return markup


def get_support_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
        types.KeyboardButton("📞 CONTACT OWNER"),
        types.KeyboardButton("🔚 BACK")
    )
    return markup


def get_back_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("🔚 BACK")
    )
    return markup


def get_payment_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=1
    )
    markup.add(
        types.KeyboardButton("❌ ORDER CANCEL")
    )
    return markup


# ============================================================
# START COMMAND
# ============================================================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    if user_id in user_states:
        del user_states[user_id]

    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": message.from_user.username, "first_name": message.from_user.first_name}},
        upsert=True
    )

    welcome_text = (
        "💎 *WELCOME TO R2F OFFICIAL PREMIUM STORE* ✅\n\n"
        "✨ *SAFE, FAST & SECURE SERVICES* 🛡️\n\n"
        "👉 *APNA PLATFORM SELECT KAREIN:* 👇"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_platform_keyboard(user_id),
    )


# ============================================================
# PLATFORM SELECTION & BACK BUTTONS (SILENT & CLEAN)
# ============================================================

@bot.message_handler(func=lambda message: message.text in ["🔙 BACK", "🔚 BACK"])
def handle_platform_back(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    if user_id == ADMIN_ID and user_id in user_states:
        state = user_states[user_id]
        st_type = state.get("type")
        if st_type in ["waiting_upi_qr_photo", "waiting_custom_qr_amount"]:
            user_states[ADMIN_ID] = {"type": "qr_manager"}
            bot.send_message(message.chat.id, "⚡ *QR CODE MANAGER*", parse_mode="Markdown", reply_markup=get_qr_manager_reply_keyboard())
            return
        elif st_type in ["waiting_loader_apk", "waiting_loader_video", "waiting_select_apk_loader", "waiting_select_video_loader", "delete_menu_choice", "waiting_delete_single_key", "waiting_delete_all_select_dur"]:
            user_states[ADMIN_ID] = {"type": "android_manager"}
            bot.send_message(message.chat.id, "📂 *ANDROID MANAGER*", parse_mode="Markdown", reply_markup=get_android_manager_reply_keyboard())
            return
        elif st_type in ["waiting_ios_download_link", "waiting_ios_video_link", "waiting_select_ios_link_loader", "waiting_select_ios_video_loader", "ios_delete_menu_choice", "waiting_ios_delete_single_key", "waiting_ios_delete_all_select_dur"]:
            user_states[ADMIN_ID] = {"type": "ios_manager"}
            bot.send_message(message.chat.id, "🍏 *iOS MANAGER*", parse_mode="Markdown", reply_markup=get_ios_manager_reply_keyboard())
            return
        elif st_type in ["waiting_single_key", "waiting_bulk_keys", "waiting_key_method", "waiting_select_android_key_dur"]:
            user_states[ADMIN_ID] = {"type": "android_manager"}
            bot.send_message(message.chat.id, "📂 *ANDROID MANAGER*", parse_mode="Markdown", reply_markup=get_android_manager_reply_keyboard())
            return
        elif st_type in ["waiting_select_ios_key_dur"]:
            user_states[ADMIN_ID] = {"type": "ios_manager"}
            bot.send_message(message.chat.id, "🍏 *iOS MANAGER*", parse_mode="Markdown", reply_markup=get_ios_manager_reply_keyboard())
            return
        elif st_type in ["qr_manager", "android_manager", "ios_manager"]:
            del user_states[ADMIN_ID]
            bot.send_message(message.chat.id, "👑 *SUPER ADMIN PANEL*", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
            return

    if user_id in user_states:
        if "qr_msg_id" in user_states[user_id]:
            try:
                bot.delete_message(message.chat.id, user_states[user_id]["qr_msg_id"])
            except Exception:
                pass
        del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "👉 *APNA PLATFORM SELECT KAREIN:*",
        parse_mode="Markdown",
        reply_markup=get_platform_keyboard(user_id),
    )


@bot.message_handler(func=lambda message: message.text == "🤖 ANDROID")
def handle_android_platform(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return
    bot.send_message(
        message.chat.id,
        "🤖 *ANDROID SECTION:*",
        parse_mode="Markdown",
        reply_markup=get_android_main_keyboard(user_id),
    )


@bot.message_handler(func=lambda message: message.text == "🍏 iOS")
def handle_ios_platform(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return
    bot.send_message(
        message.chat.id,
        "🍏 *iOS SECTION:*",
        parse_mode="Markdown",
        reply_markup=get_ios_main_keyboard(user_id),
    )


# ============================================================
# BROADCAST FEATURE HANDLER (ADMIN)
# ============================================================

@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.text == "📢 BROADCAST")
def broadcast_prompt(message):
    user_states[ADMIN_ID] = {"type": "waiting_broadcast_message"}
    bot.send_message(
        message.chat.id,
        "📢 *BROADCAST MESSAGE*\n\n💬 Jo message sabhi users ko bhejna hai, woh yahan send karein:",
        parse_mode="Markdown",
        reply_markup=get_back_reply_keyboard()
    )


# ============================================================
# GENERATE KEY MENU HANDLER (FOR ADMIN)
# ============================================================

@bot.message_handler(func=lambda message: message.text == "🔑 GENERATE KEY")
def handle_gen_key_menu(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    durations = ["5 Hour", "1 Day", "2 Day", "3 Day", "7 Day", "30 Day"]
    for d in durations:
        cb_val = d.replace(" ", "_")
        markup.add(
            types.InlineKeyboardButton(
                f"⏱ {d.upper()}",
                callback_data=f"genkey_android_{cb_val}"
            )
        )

    bot.send_message(
        message.chat.id,
        "🔑 *GENERATE ANDROID KEY*\n\nDURATION SELECT KAREIN:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("genkey_"))
def handle_genkey_callback(call):
    user_id = call.from_user.id
    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ UNAUTHORIZED!", show_alert=True)
        return

    parts = call.data.split("_")
    platform = parts[1]
    duration = "_".join(parts[2:]).replace("_", " ")
    bot.answer_callback_query(call.id)

    query_filter = {"platform": platform, "duration": duration, "status": "unused"}
    key_row = keys_collection.find_one_and_update(
        query_filter,
        {
            "$set": {
                "status": "used",
                "assigned_to": user_id,
                "assigned_at": time.time()
            }
        },
        return_document=True
    )

    if not key_row:
        bot.send_message(
            call.message.chat.id,
            f"❌ *OUT OF STOCK!*\nDURATION *{duration}* ({platform.upper()}) KE LIYE KOI UNUSED KEY AVAILABLE NAHI HAI.",
            parse_mode="Markdown"
        )
        return

    kid = key_row["id"]
    license_key = key_row["license_key"]

    bot.send_message(
        call.message.chat.id,
        f"✅ *KEY GENERATED SUCCESSFULLY!*\n\n• *PLATFORM:* {platform.upper()}\n• *ID:* `{kid}`\n• *DURATION:* {duration} ✨\n• *KEY:* `{license_key}` 💎",
        parse_mode="Markdown",
    )


# ============================================================
# SUPER ADMIN PANEL & REPLY MENU MANAGERS
# ============================================================

@bot.message_handler(func=lambda message: message.text == "👑 SUPER ADMIN")
def super_admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ YOU ARE NOT AUTHORIZED!")
        return

    bot.send_message(
        message.chat.id,
        "👑 *SUPER ADMIN PANEL*:\n\nNICHE DIYE GAYE OPTIONS MEIN SE SELECT KAREIN:",
        parse_mode="Markdown",
        reply_markup=get_super_admin_reply_keyboard(),
    )


@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.text == "⚡ QR CODE MANAGER")
def sa_qr_manager_handler(message):
    user_states[ADMIN_ID] = {"type": "qr_manager"}
    bot.send_message(
        message.chat.id,
        "⚡ *QR CODE MANAGER*:",
        parse_mode="Markdown",
        reply_markup=get_qr_manager_reply_keyboard(),
    )


@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.text == "📂 ANDROID MANAGER")
def sa_android_manager_handler(message):
    user_states[ADMIN_ID] = {"type": "android_manager"}
    bot.send_message(
        message.chat.id,
        "📂 *ANDROID MANAGER*:",
        parse_mode="Markdown",
        reply_markup=get_android_manager_reply_keyboard(),
    )


@bot.message_handler(func=lambda message: message.from_user.id == ADMIN_ID and message.text == "🍏 iOS MANAGER")
def sa_ios_manager_handler(message):
    user_states[ADMIN_ID] = {"type": "ios_manager"}
    bot.send_message(
        message.chat.id,
        "🍏 *iOS MANAGER*:",
        parse_mode="Markdown",
        reply_markup=get_ios_manager_reply_keyboard(),
    )


# ============================================================
# ADMIN REPLY MENU TEXT ROUTING & STATE INPUT
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.from_user.id in user_states,
    content_types=["text", "document", "photo", "video", "audio", "voice"]
)
def handle_admin_state_input(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    action_type = state["type"]
    text = (message.text or "").strip()

    if text in ["🔚 BACK", "🔙 BACK"]:
        handle_platform_back(message)
        return

    if action_type == "qr_manager":
        if text == "🖼️ CHANGE UPI QR":
            user_states[ADMIN_ID] = {"type": "waiting_upi_qr_photo"}
            bot.send_message(message.chat.id, "🖼️ *CHANGE UPI QR CODE*\n\n💬 APNA NEW UPI QR CODE IMAGE (.jpg/.png) YAHAN CHAT MEIN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        elif text == "🎨 GENERATE CUSTOM QR":
            user_states[ADMIN_ID] = {"type": "waiting_custom_qr_amount"}
            bot.send_message(message.chat.id, "🎨 *GENERATE CUSTOM QR*\n\n💬 AMOUNT ENTER KAREIN (JAISE: `99` YA `199`):", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        return

    if action_type == "android_manager":
        if text == "📂 ADD / UPDATE ANDROID APK":
            user_states[ADMIN_ID] = {"type": "waiting_select_apk_loader"}
            bot.send_message(message.chat.id, "📂 *SELECT ANDROID LOADER TO UPLOAD APK:*", parse_mode="Markdown", reply_markup=get_android_loader_reply_keyboard())
        elif text == "📺 ADD / UPDATE ANDROID SETUP VIDEO":
            user_states[ADMIN_ID] = {"type": "waiting_select_video_loader"}
            bot.send_message(message.chat.id, "📺 *SELECT ANDROID LOADER FOR SETUP VIDEO LINK:*", parse_mode="Markdown", reply_markup=get_android_loader_reply_keyboard())
        elif text == "🔑 ADD ANDROID KEYS (SINGLE & BULK)":
            user_states[ADMIN_ID] = {"type": "waiting_select_android_key_dur", "platform": "android"}
            bot.send_message(message.chat.id, "🔑 *ADD ANDROID KEYS*\n\nDURATION SELECT KAREIN:", parse_mode="Markdown", reply_markup=get_android_durations_reply_keyboard())
        elif text == "🪣 DELETE ANDROID KEYS":
            user_states[ADMIN_ID] = {"type": "delete_menu_choice", "platform": "android"}
            bot.send_message(message.chat.id, "🪣 *DELETE ANDROID KEYS*\n\nOPTION SELECT KAREIN:", parse_mode="Markdown", reply_markup=get_delete_options_reply_keyboard())
        return

    if action_type == "ios_manager":
        if text == "📥 ADD / UPDATE iOS DOWNLOAD LINK":
            user_states[ADMIN_ID] = {"type": "waiting_select_ios_link_loader"}
            bot.send_message(message.chat.id, "📥 *SELECT iOS LOADER FOR DOWNLOAD LINK:*", parse_mode="Markdown", reply_markup=get_ios_loader_reply_keyboard())
        elif text == "📺 ADD / UPDATE iOS SETUP VIDEO":
            user_states[ADMIN_ID] = {"type": "waiting_select_ios_video_loader"}
            bot.send_message(message.chat.id, "📺 *SELECT iOS LOADER FOR SETUP VIDEO:*", parse_mode="Markdown", reply_markup=get_ios_loader_reply_keyboard())
        elif text == "🔑 ADD iOS KEYS (SINGLE & BULK)":
            user_states[ADMIN_ID] = {"type": "waiting_select_ios_key_dur", "platform": "ios"}
            bot.send_message(message.chat.id, "🔑 *ADD iOS KEYS*\n\nDURATION SELECT KAREIN:", parse_mode="Markdown", reply_markup=get_ios_durations_reply_keyboard())
        elif text == "🪣 DELETE iOS KEYS":
            user_states[ADMIN_ID] = {"type": "ios_delete_menu_choice", "platform": "ios"}
            bot.send_message(message.chat.id, "🪣 *DELETE iOS KEYS*\n\nOPTION SELECT KAREIN:", parse_mode="Markdown", reply_markup=get_delete_options_reply_keyboard())
        return

    # Delete Menu Choice (Single vs All) for Android/iOS
    if action_type in ["delete_menu_choice", "ios_delete_menu_choice"]:
        platform = state["platform"]
        if text == "🗑️ DELETE SINGLE KEY":
            if platform == "android":
                user_states[ADMIN_ID] = {"type": "waiting_delete_single_key", "platform": "android"}
            else:
                user_states[ADMIN_ID] = {"type": "waiting_ios_delete_single_key", "platform": "ios"}
            bot.send_message(message.chat.id, f"🗑️ *DELETE SINGLE KEY ({platform.upper()})*\n\n💬 Jiss key ko delete karna hai, woh **license key** yahan send karein:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        elif text == "🗑️ DELETE ALL KEYS":
            if platform == "android":
                user_states[ADMIN_ID] = {"type": "waiting_delete_all_select_dur", "platform": "android"}
                bot.send_message(message.chat.id, "🗑️ *DELETE ALL KEYS (ANDROID)*\n\nDURATION SET SELECT KAREIN JISE DELETE KARNA HAI:", parse_mode="Markdown", reply_markup=get_android_durations_reply_keyboard())
            else:
                user_states[ADMIN_ID] = {"type": "waiting_ios_delete_all_select_dur", "platform": "ios"}
                bot.send_message(message.chat.id, "🗑️ *DELETE ALL KEYS (iOS)*\n\nDURATION SET SELECT KAREIN JISE DELETE KARNA HAI:", parse_mode="Markdown", reply_markup=get_ios_durations_reply_keyboard())
        return

    # Handling Single Key Deletion by text
    if action_type in ["waiting_delete_single_key", "waiting_ios_delete_single_key"]:
        platform = state["platform"]
        res = keys_collection.delete_one({"platform": platform, "license_key": text})
        if res.deleted_count > 0:
            bot.reply_to(message, f"✅ *SUCCESSFULLY DELETED KEY:* `{text}` 🗑️", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        else:
            bot.reply_to(message, f"❌ *KEY NOT FOUND:* `{text}`\nKripya sahi key enter karein.", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        del user_states[ADMIN_ID]
        return

    # Handling Delete All Keys by selected duration set
    if action_type in ["waiting_delete_all_select_dur", "waiting_ios_delete_all_select_dur"]:
        if text.startswith("⏱ "):
            dur = text.replace("⏱ ", "")
            platform = state["platform"]
            res = keys_collection.delete_many({"platform": platform, "duration": dur})
            bot.send_message(message.chat.id, f"✅ *ALL KEYS DELETED SUCCESSFULLY!*\n\n• Platform: `{platform.upper()}`\n• Duration Set: `{dur}`\n• Total Deleted: `{res.deleted_count}` keys 🗑️", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
            del user_states[ADMIN_ID]
        return

    # Loader selection for Android APK/Video
    if action_type in ["waiting_select_apk_loader", "waiting_select_video_loader"]:
        loader_map = {
            "⚙️ VOLTAGE LOADER": "voltage_loader",
            "🚀 VIP LOADER": "vip_loader",
            "💎 NICE X NEXA": "nicexnexa",
            "⚡ NICE X NEXA SERVER": "nicexnexaserver"
        }
        if text in loader_map:
            l_key = loader_map[text]
            if action_type == "waiting_select_apk_loader":
                user_states[ADMIN_ID] = {"type": "waiting_loader_apk", "loader_key": l_key}
                bot.send_message(message.chat.id, f"📂 *UPLOAD APK FOR {text}*\n\n💬 AB APNI **APK FILE (.apk)** YAHAN CHAT MEIN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
            else:
                user_states[ADMIN_ID] = {"type": "waiting_loader_video", "loader_key": l_key}
                bot.send_message(message.chat.id, f"📺 *ADD SETUP VIDEO LINK FOR {text}*\n\n💬 AB APNA **SETUP VIDEO LINK** YAHAN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        return

    # Loader selection for iOS Link/Video
    if action_type in ["waiting_select_ios_link_loader", "waiting_select_ios_video_loader"]:
        ios_map = {
            "🍏 WIN iOS": "win_ios",
            "👑 KING iOS": "king_ios"
        }
        if text in ios_map:
            l_key = ios_map[text]
            if action_type == "waiting_select_ios_link_loader":
                user_states[ADMIN_ID] = {"type": "waiting_ios_download_link", "loader_key": l_key}
                bot.send_message(message.chat.id, f"📥 *ADD DOWNLOAD LINK FOR {text}*\n\n💬 AB APNA **DOWNLOAD LINK** YAHAN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
            else:
                user_states[ADMIN_ID] = {"type": "waiting_ios_video_link", "loader_key": l_key}
                bot.send_message(message.chat.id, f"📺 *ADD SETUP VIDEO LINK FOR {text}*\n\n💬 AB APNA **SETUP VIDEO LINK** YAHAN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        return

    # Duration selection for adding keys
    if action_type in ["waiting_select_android_key_dur", "waiting_select_ios_key_dur"]:
        if text.startswith("⏱ "):
            dur = text.replace("⏱ ", "")
            platform = state["platform"]
            user_states[ADMIN_ID] = {"type": "waiting_key_method", "platform": platform, "duration": dur}
            bot.send_message(message.chat.id, f"⏱ PLATFORM: *{platform.upper()}* | DURATION: *{dur}*\n\nKAUNSA METHOD USE KARNA HAI SELECT KAREIN:", parse_mode="Markdown", reply_markup=get_key_method_reply_keyboard())
        return

    # Key method selection (Single / Bulk)
    if action_type == "waiting_key_method":
        platform = state["platform"]
        duration = state["duration"]
        if text == "➕ ADD SINGLE KEY":
            user_states[ADMIN_ID] = {"type": "waiting_single_key", "platform": platform, "duration": duration}
            bot.send_message(message.chat.id, f"➕ *ADD SINGLE KEY ({platform.upper()})*\n\nDURATION: *{duration}*\n\n💬 APNI **LICENSE KEY** YAHAN CHAT MEIN SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        elif text == "📦 ADD BULK KEYS":
            user_states[ADMIN_ID] = {"type": "waiting_bulk_keys", "platform": platform, "duration": duration}
            bot.send_message(message.chat.id, f"📦 *ADD BULK KEYS ({platform.upper()})*\n\nDURATION: *{duration}*\n\n💬 MULTIPLE KEYS **EK LINE MEIN EK KEY** KARKE YAHAN PASTE/SEND KAREIN:", parse_mode="Markdown", reply_markup=get_back_reply_keyboard())
        return

    if action_type == "waiting_broadcast_message":
        if text in ["🔚 BACK", "🔙 BACK"]:
            handle_platform_back(message)
            return

        del user_states[ADMIN_ID]

        users = list(users_collection.find({}, {"user_id": 1}))
        total_users = len(users)

        if total_users == 0:
            bot.reply_to(message, "❌ Database mein koi users nahi mile!")
            return

        sent_count = 0
        fail_count = 0

        status_msg = bot.send_message(message.chat.id, f"📢 Broadcast started for `{total_users}` users...", parse_mode="Markdown")

        for u in users:
            uid = u["user_id"]
            if uid == ADMIN_ID:
                continue
            try:
                bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.id)
                sent_count += 1
                time.sleep(0.04)
            except Exception:
                fail_count += 1

        bot.edit_message_text(
            f"✅ *BROADCAST COMPLETED!*\n\n"
            f"• *Total Users:* `{total_users}`\n"
            f"• *Successfully Sent:* `{sent_count}`\n"
            f"• *Failed / Blocked:* `{fail_count}`",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
        return

    if action_type == "waiting_upi_qr_photo":
        if not message.photo:
            bot.reply_to(message, "❌ KRIPYA EK VALID QR IMAGE PHOTO SEND KAREIN!")
            return
        file_id = message.photo[-1].file_id
        loaders_collection.update_one({"loader_key": "static_upi_qr"}, {"$set": {"file_id": file_id}}, upsert=True)
        del user_states[user_id]
        bot.reply_to(message, "✅ *STATIC UPI QR SUCCESSFULLY SAVED!*", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        return

    if action_type == "waiting_custom_qr_amount":
        try:
            amount = int(text)
            del user_states[user_id]
            unique_tr = f"R2FCUST{int(time.time())}"
            upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
            qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"
            bot.send_photo(message.chat.id, photo=qr_api_url, caption=f"🎨 *CUSTOM PAYMENT QR*\n\n• *AMOUNT:* ₹{amount}\n• *UPI ID:* `{UPI_ID}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        except Exception:
            bot.reply_to(message, "❌ KRIPYA SAHI AMOUNT ENTER KAREIN!")
        return

    if action_type == "waiting_loader_apk":
        loader_key = state["loader_key"]
        if not message.document:
            bot.reply_to(message, "❌ KRIPYA EK VALID APK DOCUMENT FILE SEND KAREIN!")
            return
        file_id = message.document.file_id
        file_name = message.document.file_name or "app.apk"
        loaders_collection.update_one({"loader_key": loader_key}, {"$set": {"file_id": file_id, "file_name": file_name}}, upsert=True)
        del user_states[user_id]
        bot.reply_to(message, f"✅ *APK SUCCESSFULLY SAVED FOR {loader_key.upper().replace('_', ' ')}!*\n\n• *File Name:* `{file_name}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        return

    if action_type == "waiting_loader_video":
        loader_key = state["loader_key"]
        video_link = text
        if not video_link:
            bot.reply_to(message, "❌ KRIPYA VALID VIDEO LINK SEND KAREIN!")
            return
        loaders_collection.update_one({"loader_key": loader_key}, {"$set": {"video_link": video_link}}, upsert=True)
        del user_states[user_id]
        bot.reply_to(message, f"✅ *SETUP VIDEO LINK SAVED FOR {loader_key.upper().replace('_', ' ')}!*\n\n• *Link:* `{video_link}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        return

    if action_type == "waiting_ios_download_link":
        loader_key = state["loader_key"]
        download_link = text
        if not download_link:
            bot.reply_to(message, "❌ KRIPYA VALID DOWNLOAD LINK SEND KAREIN!")
            return
        loaders_collection.update_one({"loader_key": f"ios_{loader_key}"}, {"$set": {"download_link": download_link}}, upsert=True)
        del user_states[user_id]
        bot.reply_to(message, f"✅ *iOS DOWNLOAD LINK SAVED FOR {loader_key.upper().replace('_', ' ')}!*\n\n• *Link:* `{download_link}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        return

    if action_type == "waiting_ios_video_link":
        loader_key = state["loader_key"]
        video_link = text
        if not video_link:
            bot.reply_to(message, "❌ KRIPYA VALID VIDEO LINK SEND KAREIN!")
            return
        loaders_collection.update_one({"loader_key": f"ios_{loader_key}"}, {"$set": {"video_link": video_link}}, upsert=True)
        del user_states[user_id]
        bot.reply_to(message, f"✅ *iOS SETUP VIDEO LINK SAVED FOR {loader_key.upper().replace('_', ' ')}!*\n\n• *Link:* `{video_link}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        return

    if text.startswith("/") or text in ["🤖 ANDROID", "🍏 iOS", "👑 SUPER ADMIN", "📢 BROADCAST", "💬 CONTACT SUPPORT"]:
        del user_states[user_id]
        return

    if action_type == "waiting_single_key":
        duration = state["duration"]
        platform = state.get("platform", "android")
        try:
            new_id = get_next_id("keys")
            keys_collection.insert_one({"id": new_id, "platform": platform, "duration": duration, "license_key": text, "status": "unused", "assigned_to": None})
            del user_states[user_id]
            bot.reply_to(message, f"✅ *SINGLE KEY ADDED ({platform.upper()})!*\n\n• *DURATION:* {duration}\n• *KEY:* `{text}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())
        except DuplicateKeyError:
            bot.reply_to(message, "❌ *DUPLICATE KEY ERROR!*\nYEH LICENSE KEY PEHLE SE DATABASE MEIN MOJOOD HAI.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ KEY ADD KARTE WAQT ERROR AAYA.")

    elif action_type == "waiting_bulk_keys":
        duration = state["duration"]
        platform = state.get("platform", "android")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            bot.reply_to(message, "❌ KOI KEYS NAHI MILI!")
            return

        added_count, duplicate_count = 0, 0
        for key in lines:
            try:
                new_id = get_next_id("keys")
                keys_collection.insert_one({"id": new_id, "platform": platform, "duration": duration, "license_key": key, "status": "unused", "assigned_to": None})
                added_count += 1
            except DuplicateKeyError:
                duplicate_count += 1

        del user_states[user_id]
        bot.reply_to(message, f"📦 *BULK KEYS REPORT ({platform.upper()})*\n\n• *DURATION:* {duration}\n• *ADDED:* `{added_count}`\n• *DUPLICATES SKIPPED:* `{duplicate_count}`", parse_mode="Markdown", reply_markup=get_super_admin_reply_keyboard())


# ============================================================
# SUPER ADMIN DELETE CALLBACK HANDLER
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("sa_del_id_"))
def super_admin_delete_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ UNAUTHORIZED!", show_alert=True)
        return

    kid = int(call.data.split("_")[3])
    result = keys_collection.delete_one({"id": kid})
    bot.answer_callback_query(call.id, f"✅ KEY SUCCESSFULLY DELETED!", show_alert=True)
    try:
        if result.deleted_count:
            bot.edit_message_text(f"✅ *KEY SUCCESSFULLY DELETED!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *KEY ALREADY DELETED!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    except Exception:
        pass


# ============================================================
# REPLY MENUS (ANDROID & iOS)
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.text in [
            "🛒 PURCHASE KEY",
            "🔐 MY KEYS",
            "♻️ APK & SETUP",
            "💬 CONTACT SUPPORT",
            "🛒 PURCHASE KEY (iOS)",
            "📥 DOWNLOAD LINK"
        ]
)
def handle_reply_menu(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    if user_id in user_states:
        del user_states[user_id]

    text = message.text

    if text == "🛒 PURCHASE KEY":
        markup = types.InlineKeyboardMarkup(row_width=2)
        plans = [
            ("⏱ 5 HOUR - ₹30", "5 Hour", 30),
            ("⏱ 1 DAY - ₹99", "1 Day", 99),
            ("⏱ 2 DAY - ₹149", "2 Day", 149),
            ("⏱ 3 DAY - ₹199", "3 Day", 199),
            ("⏱ 7 DAY - ₹399", "7 Day", 399),
            ("⏱ 30 DAY - ₹799", "30 Day", 799),
        ]
        for title, duration, amount in plans:
            stock_count = keys_collection.count_documents({"platform": "android", "duration": duration, "status": "unused"})
            button_title = f"{title} | STOCK: {stock_count}"
            cb_duration = duration.replace(" ", "_")
            markup.add(types.InlineKeyboardButton(button_title, callback_data=f"plan_android_{cb_duration}_{amount}"))

        bot.send_message(message.chat.id, "📋 *SELECT ANDROID PLAN*:\n\nAPNA PLAN SELECT KAREIN:", parse_mode="Markdown", reply_markup=markup)

    elif text == "🛒 PURCHASE KEY (iOS)":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🍏 WIN iOS", callback_data="ios_plan_win_ios"),
            types.InlineKeyboardButton("👑 KING iOS", callback_data="ios_plan_king_ios")
        )
        bot.send_message(message.chat.id, "🍏 *SELECT iOS LOADER*:\n\nKIS LOADER KE LIYE KEY CHAHIYE SELECT KAREIN:", parse_mode="Markdown", reply_markup=markup)

    elif text == "🔐 MY KEYS":
        current_time = time.time()
        all_keys = list(keys_collection.find({"status": "used", "assigned_to": user_id}))
        
        valid_keys = []
        for key in all_keys:
            duration = key.get("duration", "1 Day")
            assigned_at = key.get("assigned_at", current_time)
            duration_secs = parse_duration_seconds(duration)
            if current_time - (assigned_at or current_time) > duration_secs:
                keys_collection.delete_one({"id": key["id"]})
            else:
                valid_keys.append(key)

        if not valid_keys:
            bot.send_message(message.chat.id, "❌ AAPKE PAAS KOI ACTIVE KEY NAHI HAI!", parse_mode="Markdown")
            return

        for key in valid_keys:
            key_id = key["id"]
            platform = key.get("platform", "android").upper()
            duration = key["duration"]
            license_key = key["license_key"]
            assigned_at = key.get("assigned_at", current_time)
            date_str = time.strftime('%d-%m-%Y %H:%M', time.localtime(assigned_at))

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🔄 RESET", callback_data=f"reset_{license_key}"),
                types.InlineKeyboardButton("🪣 DELETE", callback_data=f"delmykey_{key_id}"),
            )

            bot.send_message(
                message.chat.id,
                f"💎 *PLATFORM:* {platform} | *PLAN:* {duration}\n📅 *DATE:* {date_str}\n🔑 `{license_key}`",
                parse_mode="Markdown",
                reply_markup=markup
            )

    elif text == "♻️ APK & SETUP":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚙️ VOLTAGE LOADER", callback_data="setup_voltage_loader"),
            types.InlineKeyboardButton("🚀 VIP LOADER", callback_data="setup_vip_loader"),
            types.InlineKeyboardButton("💎 NICE X NEXA", callback_data="setup_nicexnexa"),
            types.InlineKeyboardButton("⚡ NICE X NEXA SERVER", callback_data="setup_nicexnexaserver"),
        )
        bot.send_message(message.chat.id, "♻ *SELECT LOADER/SERVER FOR SETUP & APK:*", parse_mode="Markdown", reply_markup=markup)

    elif text == "📥 DOWNLOAD LINK":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🍏 WIN iOS", callback_data="download_ios_win_ios"),
            types.InlineKeyboardButton("👑 KING iOS", callback_data="download_ios_king_ios"),
        )
        bot.send_message(message.chat.id, "📥 *SELECT iOS LOADER FOR DOWNLOAD LINK:*", parse_mode="Markdown", reply_markup=markup)

    elif text == "💬 CONTACT SUPPORT":
        user_states[user_id] = {"type": "support"}
        bot.send_message(
            message.chat.id,
            "💬 *WELCOME TO SUPPORT CHAT!*\n\nAPNA MESSAGE YAHAN SEND KAREIN, ADMIN AAPKO JALD REPLY KAREGA.",
            parse_mode="Markdown",
            reply_markup=get_support_reply_keyboard(),
        )


# ============================================================
# iOS PLANS & DOWNLOAD CALLBACKS
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("ios_plan_"))
def handle_ios_plan_selection(call):
    if is_blocked(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    loader_type = call.data.replace("ios_plan_", "")
    loader_title = loader_type.upper().replace("_", " ")

    markup = types.InlineKeyboardMarkup(row_width=1)
    ios_plans = [
        ("⏱ 1 DAY - ₹150", "1 Day", 150),
        ("⏱ 7 DAY - ₹899", "7 Day", 899),
        ("⏱ 30 DAY - ₹1599", "30 Day", 1599),
    ]
    for title, duration, amount in ios_plans:
        stock_count = keys_collection.count_documents({"platform": "ios", "duration": duration, "status": "unused"})
        btn_text = f"{title} | STOCK: {stock_count}"
        cb_dur = duration.replace(" ", "_")
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"plan_ios_{cb_dur}_{amount}"))

    bot.send_message(call.message.chat.id, f"🍏 *SELECT PLAN FOR {loader_title}*:\n\nAPNA PLAN SELECT KAREIN:", parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("download_ios_"))
def handle_ios_download_callback(call):
    if is_blocked(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    loader_key = call.data.replace("download_ios_", "")
    doc_key = f"ios_{loader_key}"

    loader_doc = loaders_collection.find_one({"loader_key": doc_key})
    download_link = loader_doc.get("download_link", f"https://t.me/{OWNER_USERNAME}") if loader_doc else f"https://t.me/{OWNER_USERNAME}"
    video_link = loader_doc.get("video_link", f"https://t.me/{OWNER_USERNAME}") if loader_doc else f"https://t.me/{OWNER_USERNAME}"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📥 DOWNLOAD APP", url=download_link),
        types.InlineKeyboardButton("📺 WATCH SETUP VIDEO", url=video_link)
    )
    bot.send_message(
        call.message.chat.id,
        f"🍏 *HERE IS YOUR DOWNLOAD LINK FOR {loader_key.upper().replace('_', ' ')}*:\n\nNICHE DIYE GAYE BUTTON SE APP DOWNLOAD KAREIN AUR SETUP VIDEO DEHEIN:",
        parse_mode="Markdown",
        reply_markup=markup
    )


# ============================================================
# SETUP CALLBACKS (ANDROID)
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("setup_"))
def handle_setup_callbacks(call):
    if is_blocked(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    key = call.data.replace("setup_", "")

    loader_doc = loaders_collection.find_one({"loader_key": key})
    video_link = loader_doc.get("video_link", f"https://t.me/{OWNER_USERNAME}") if loader_doc else f"https://t.me/{OWNER_USERNAME}"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📺 WATCH SETUP VIDEO", url=video_link)
    )

    if loader_doc and "file_id" in loader_doc:
        file_id = loader_doc["file_id"]
        try:
            bot.send_document(
                call.message.chat.id,
                document=file_id,
                caption=f"📁 *HERE IS YOUR APK FOR {key.upper().replace('_', ' ')}*:\n\nNICHE DIYE GAYE BUTTON SE SETUP VIDEO DEHEIN:",
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception:
            bot.send_message(call.message.chat.id, f"❌ APK SEND KARNE MEIN ERROR AAYA.\n\n📺 WATCH SETUP VIDEO LINK:", parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, f"❌ *APK NOT AVAILABLE YET!*\n\n📺 WATCH SETUP VIDEO LINK:", parse_mode="Markdown", reply_markup=markup)


# ============================================================
# SUPPORT CHAT MESSAGE HANDLER
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id != ADMIN_ID
        and message.from_user.id in user_states
        and user_states[message.from_user.id].get("type") == "support",
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def handle_support_chat_messages(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    text = (message.text or "").strip()

    if text == "🔚 BACK":
        if user_id in user_states:
            del user_states[user_id]
        bot.send_message(
            message.chat.id,
            "🏠 *MAIN MENU:*",
            parse_mode="Markdown",
            reply_markup=get_platform_keyboard(user_id),
        )
        return

    if text == "📞 CONTACT OWNER":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 OPEN OWNER DM", url=f"https://t.me/{OWNER_USERNAME}"))
        bot.send_message(
            message.chat.id,
            f"💬 *CLICK THE BUTTON BELOW TO OPEN OWNER DM DIRECTLY:*\n\n👉 Telegram: https://t.me/{OWNER_USERNAME}",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    forward_message_to_admin(message)


# ============================================================
# HANDLE DELETE MY KEY
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmykey_"))
def handle_delete_my_key(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return

    try:
        key_id = int(call.data.split("_")[1])
    except Exception:
        bot.answer_callback_query(call.id, "❌ INVALID KEY ID!", show_alert=True)
        return

    result = keys_collection.delete_one({"id": key_id, "assigned_to": user_id})
    if result.deleted_count > 0:
        bot.answer_callback_query(call.id, "✅ KEY SUCCESSFULLY DELETE KAR DI GAYI HAI!", show_alert=True)
        try:
            bot.edit_message_text("❌ *KEY SUCCESSFULLY DELETE KAR DI GAYI HAI!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "❌ YEH KEY AAPKO ASSIGNED NAHI HAI YA PEHLE HI DELETE HO CHUKI HAI!", show_alert=True)


# ============================================================
# HANDLE PLAN (PURCHASE) - ANDROID & iOS
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def handle_plan(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    platform = parts[1] # android or ios
    amount = int(parts[-1])
    duration = "_".join(parts[2:-1]).replace("_", " ")
    current_time = time.time()

    order_id = get_next_id("orders")
    orders_collection.insert_one({"id": order_id, "user_id": user_id, "platform": platform, "duration": duration, "amount": amount, "created_at": current_time, "status": "pending"})

    static_qr_doc = loaders_collection.find_one({"loader_key": "static_upi_qr"})

    caption_text = (
        "💳 *SCAN & PAY*\n\n"
        f"• *PLATFORM:* {platform.upper()}\n"
        f"• *PLAN:* {duration}\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n\n"
        "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
        "1️⃣ PEHLE PAYMENT KAREIN.\n"
        "2️⃣ APNE **PAYMENT SCREENSHOT** KO YAHIN CHAT MEIN SEND KAREIN."
    )

    if static_qr_doc and "file_id" in static_qr_doc:
        sent_msg = bot.send_photo(
            chat_id=call.message.chat.id,
            photo=static_qr_doc["file_id"],
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=get_payment_reply_keyboard(),
        )
    else:
        unique_tr = f"R2F{order_id}{int(current_time)}"
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

        sent_msg = bot.send_photo(
            chat_id=call.message.chat.id,
            photo=qr_api_url,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=get_payment_reply_keyboard(),
        )

    user_states[user_id] = {
        "type": "plan",
        "order_id": order_id,
        "platform": platform,
        "duration": duration,
        "amount": amount,
        "timestamp": current_time,
        "qr_msg_id": sent_msg.message_id,
    }

    threading.Thread(
        target=send_timeout_failed_message,
        args=(call.message.chat.id, user_id, order_id),
        daemon=True,
    ).start()


# ============================================================
# HANDLE SCREENSHOT
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id in user_states
        and user_states[message.from_user.id]["type"] == "plan",
    content_types=["text", "photo"],
)
def handle_user_payment_input(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    state = user_states[user_id]

    if message.text:
        text = message.text.strip()
        if "ORDER CANCEL" in text.upper():
            handle_cancel_button(message)
            return

        if any(menu_item in text.upper() for menu_item in ["🤖 ANDROID", "🍏 iOS", "👑 SUPER ADMIN", "📢 BROADCAST", "💬 CONTACT SUPPORT", "🔚 BACK", "🔙 BACK"]) or text.startswith("/"):
            if user_id in user_states and "qr_msg_id" in user_states[user_id]:
                try:
                    bot.delete_message(message.chat.id, user_states[user_id]["qr_msg_id"])
                except Exception:
                    pass
            del user_states[user_id]
            return

        bot.reply_to(message, "❌ KRIPYA TEXT KI JAGAH APNA **PAYMENT SCREENSHOT** BHEIN!", reply_markup=get_payment_reply_keyboard())
        return

    if message.photo:
        order_id = state["order_id"]
        platform = state["platform"]
        duration = state["duration"]
        amount = state["amount"]

        orders_collection.update_one({"id": order_id}, {"$set": {"status": "pending_admin"}})

        if "qr_msg_id" in state:
            try:
                bot.delete_message(message.chat.id, state["qr_msg_id"])
            except Exception:
                pass

        del user_states[user_id]

        bot.reply_to(
            message,
            "⏳ *SCREENSHOT SUBMITTED SUCCESSFULLY!*\nAAPKA SCREENSHOT ADMIN KE PAAS VERIFICATION KE LIYE BHEJ DIYA GAYA HAI.",
            parse_mode="Markdown",
            reply_markup=get_platform_keyboard(user_id),
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("YES", callback_data=f"adm_yes_{order_id}"),
            types.InlineKeyboardButton("NO", callback_data=f"adm_no_{order_id}"),
        )

        user_info = message.from_user
        username_str = f"@{user_info.username}" if user_info.username else "NO USERNAME"
        first_name = user_info.first_name if user_info.first_name else "USER"

        admin_text = (
            f"🔔 *NEW PAYMENT SCREENSHOT VERIFICATION!*\n\n"
            f"👤 *USER:* {first_name} ({username_str})\n"
            f"🆔 *USER ID:* `{user_id}`\n"
            f"🌐 *PLATFORM:* {platform.upper()}\n"
            f"⏱ *PLAN:* {duration}\n"
            f"💵 *AMOUNT:* ₹{amount}"
        )

        try:
            bot.send_photo(
                ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=admin_text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception:
            pass


# ============================================================
# ADMIN YES / NO CALLBACK
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_approval_callback(call):
    data = call.data
    parts = data.split("_")
    action = parts[1]
    order_id = int(parts[2])

    row = orders_collection.find_one({"id": order_id})
    if not row:
        bot.answer_callback_query(call.id, "ORDER NOT FOUND!")
        return

    user_id = row["user_id"]
    platform = row.get("platform", "android")
    duration = row["duration"]
    status = row["status"]

    if status not in ["pending", "pending_admin"]:
        bot.answer_callback_query(call.id, f"ORDER IS ALREADY {status.upper()}!", show_alert=True)
        return

    try:
        user_chat = bot.get_chat(user_id)
        u_name = user_chat.first_name if user_chat.first_name else "USER"
        u_uname = f"@{user_chat.username}" if user_chat.username else "NO USERNAME"
    except Exception:
        u_name = "USER"
        u_uname = "NO USERNAME"

    if action == "yes":
        key_row = keys_collection.find_one({"platform": platform, "duration": duration, "status": "unused"}, {"id": 1, "license_key": 1})
        if not key_row:
            bot.answer_callback_query(call.id, "❌ OUT OF STOCK!", show_alert=True)
            return

        key_id = key_row["id"]
        license_key = key_row["license_key"]

        assigned_key = keys_collection.find_one_and_update(
            {"id": key_id, "status": "unused"},
            {"$set": {"status": "used", "assigned_to": user_id, "assigned_at": time.time()}},
            return_document=True
        )

        if not assigned_key:
            bot.answer_callback_query(call.id, "❌ KEY ALREADY TAKEN.", show_alert=True)
            return

        orders_collection.update_one({"id": order_id}, {"$set": {"status": "approved"}})
        bot.answer_callback_query(call.id, "PAYMENT VERIFIED & KEY SENT!")

        try:
            bot.edit_message_caption(
                f"{call.message.caption}\n\n"
                f"STATUS: *✅ APPROVED (YES)*\n"
                f"👤 USER NAME: {u_name}\n"
                f"🔗 USERNAME: {u_uname}\n"
                f"🆔 USER ID: `{user_id}`\n"
                f"🔑 GIVEN KEY: `{license_key}`",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass

        try:
            bot.send_message(
                user_id,
                f"🎉 *PAYMENT VERIFIED & APPROVED BY ADMIN!*\n\n• *PLATFORM:* {platform.upper()}\n• *PLAN:* {duration}\n• *YOUR LICENSE KEY:*\n`{license_key}`",
                parse_mode="Markdown",
                reply_markup=get_platform_keyboard(user_id),
            )
        except Exception:
            pass

    else:
        orders_collection.delete_one({"id": order_id})
        bot.answer_callback_query(call.id, "PAYMENT REJECTED & ORDER DELETED.")

        try:
            bot.edit_message_caption(
                f"{call.message.caption}\n\nSTATUS: *❌ REJECTED & DELETED (NO)*",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass

        try:
            bot.send_message(
                user_id,
                "Madarchod payment kar fir screen shot de",
                parse_mode="Markdown",
                reply_markup=get_platform_keyboard(user_id),
            )
        except Exception:
            pass


# ============================================================
# CANCEL ORDER
# ============================================================

@bot.message_handler(func=lambda message: "ORDER CANCEL" in (message.text or "").upper())
def handle_cancel_button(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        return

    if user_id not in user_states:
        bot.send_message(message.chat.id, "❌ ACTION CANCELLED.", reply_markup=get_platform_keyboard(user_id))
        return

    state = user_states[user_id]
    order_id = state["order_id"]

    if "qr_msg_id" in state:
        try:
            bot.delete_message(message.chat.id, state["qr_msg_id"])
        except Exception:
            pass

    orders_collection.delete_one({"id": order_id})
    del user_states[user_id]

    bot.send_message(message.chat.id, "❌ PAYMENT CANCELLED SUCCESSFULLY.", reply_markup=get_platform_keyboard(user_id))


# ============================================================
# RESET KEY (CLEAN SENT TO ADMIN)
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("reset_"))
def handle_reset_key(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        bot.answer_callback_query(call.id, "❌ You are blocked!", show_alert=True)
        return

    license_key = call.data.replace("reset_", "")

    bot.answer_callback_query(call.id, "🔄 RESET REQUEST SENT TO ADMIN SUCCESSFULLY! ✅", show_alert=True)
    
    # Clean message sent to admin containing ONLY the key and request note for easy copying
    reset_msg = (
        f"`{license_key}`\n"
        f"♻️ *RESET REQUEST*"
    )
    bot.send_message(ADMIN_ID, reset_msg, parse_mode="Markdown")


# ============================================================
# CATCH-ALL: FORWARD USER MESSAGES TO ADMIN
# ============================================================

@bot.message_handler(
    func=lambda message: message.from_user.id != ADMIN_ID and message.from_user.id not in user_states,
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def forward_user_messages_to_admin_catchall(message):
    if is_blocked(message.from_user.id):
        return
    forward_message_to_admin(message)


# ============================================================
# ADMIN REPLY TO USER (AND BLOCK FEATURE)
# ============================================================

@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID and message.reply_to_message is not None,
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def handle_admin_reply(message):
    reply_msg = message.reply_to_message
    target_user_id = admin_reply_map.get(reply_msg.message_id)

    if not target_user_id:
        text_content = reply_msg.text or reply_msg.caption or ""
        match = re.search(r"USER ID:\s*`?(\d+)`?", text_content, re.IGNORECASE)
        if match:
            target_user_id = int(match.group(1))
        elif reply_msg.forward_from:
            target_user_id = reply_msg.forward_from.id

    if not target_user_id:
        bot.reply_to(message, "❌ TARGET USER ID NAHI MILA. KRIPYA USER KE **INFO MESSAGE** PAR REPLY KAREIN.", parse_mode="Markdown")
        return

    admin_text = (message.text or "").strip().lower()

    if admin_text == "block":
        try:
            blocked_collection.update_one(
                {"user_id": target_user_id},
                {"$set": {"user_id": target_user_id}},
                upsert=True
            )
            bot.reply_to(message, f"✅ User `{target_user_id}` has been **BLOCKED** successfully! 🚫", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Failed to block user: `{e}`", parse_mode="Markdown")
        return

    try:
        bot.copy_message(chat_id=target_user_id, from_chat_id=message.chat.id, message_id=message.id)
    except Exception as e:
        bot.reply_to(message, "❌ Message Not Sent", parse_mode="Markdown")


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "BOT IS ACTIVE AND RUNNING SMOOTHLY WITH MONGODB!"


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
        bot.set_my_commands([])
    except Exception as e:
        print(f"WEBHOOK CLEANUP ERROR: {e}")

    print("BOT IS RUNNING WITH FLASK + MONGODB ON RENDER...")

    bot.infinity_polling(timeout=60, long_polling_timeout=60)
