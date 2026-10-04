import os
import re
import threading
import time
import json
import queue

from flask import Flask, request, jsonify, Response
import telebot
from telebot import types
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN")
MONGODB_URI = os.environ.get("MONGODB_URI")
RENDER_EXTERNAL_URL = os.environ.get(
    "RENDER_EXTERNAL_URL",
    "https://r2fsunilyt-1.onrender.com"
)

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

ADMIN_ID = 6795305850
OWNER_USERNAME = "R2FSUNILYT"

bot = telebot.TeleBot(TOKEN)

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client_queues = {}
queues_lock = threading.Lock()


def broadcast_message(device_id, message_data):
    with queues_lock:
        if device_id in client_queues:
            json_str = json.dumps(message_data)

            for q in client_queues[device_id]:
                try:
                    q.put(json_str)
                except Exception:
                    pass


# ============================================================
# MONGODB
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
    counters_collection = db["counters"]
    payments_collection = db["payments_table"]
    device_cooldowns_collection = db["device_cooldowns"]
    chats_collection = db["chats"]

    keys_collection.create_index(
        [("license_key", ASCENDING)],
        unique=True,
        name="unique_license_key",
    )

    keys_collection.create_index(
        [("duration", ASCENDING), ("status", ASCENDING)]
    )

    keys_collection.create_index(
        [("assigned_to", ASCENDING), ("status", ASCENDING)]
    )

    payments_collection.create_index(
        [("utr", ASCENDING)],
        unique=True,
        name="unique_payment_utr"
    )

    payments_collection.create_index(
        [("payment_id", ASCENDING)],
        unique=True,
        name="unique_payment_id"
    )

    payments_collection.create_index(
        [("status", ASCENDING), ("created_at", DESCENDING)]
    )

    device_cooldowns_collection.create_index(
        [("device_id", ASCENDING)],
        unique=True
    )

    chats_collection.create_index(
        [("device_id", ASCENDING), ("timestamp", ASCENDING)],
        name="device_chat_timestamp"
    )

    print(
        "MongoDB connected successfully with "
        "Real-Time Chat, Media & Auto-Payment Approval Support!"
    )

except Exception as e:
    raise RuntimeError(f"MongoDB connection failed: {e}")


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
# PLAN NORMALIZATION
# ============================================================

PLAN_ALIASES = {
    "5 Hour": "5 Hour",
    "5 Hours": "5 Hour",

    "1 Day": "1 Day",

    "7 Day": "7 Day",
    "7 Days": "7 Day",

    "30 Day": "30 Day",
    "30 Days": "30 Day",
}


def normalize_plan(plan):
    if not plan:
        return None

    clean = str(plan).strip()

    if clean in PLAN_ALIASES:
        return PLAN_ALIASES[clean]

    for key, value in PLAN_ALIASES.items():
        if clean.lower() == key.lower():
            return value

    return None


# ============================================================
# USER STATE
# ============================================================

user_states = {}


# ============================================================
# KEYBOARDS (UPDATED WITH LIVE CHAT)
# ============================================================

def get_main_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    markup.add(
        types.KeyboardButton("🔑 GENERATE KEY"),
        types.KeyboardButton("📊 CHECK STOCK")
    )

    markup.add(
        types.KeyboardButton("➕ ADD SINGLE"),
        types.KeyboardButton("📦 ADD BULK")
    )

    markup.add(
        types.KeyboardButton("🗑️ DELETE KEY"),
        types.KeyboardButton("📋 SHOW SOLD KEY")
    )

    markup.add(
        types.KeyboardButton("💬 LIVE CHAT")
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


# ============================================================
# BOT COMMANDS
# ============================================================

def setup_bot_commands():
    commands = [
        types.BotCommand("start", "Open Control Panel / Support"),
        types.BotCommand("generate", "Generate Key Shortcut"),
        types.BotCommand("stock", "Check Stock Shortcut"),
        types.BotCommand("addsingle", "Add Single Key Shortcut"),
        types.BotCommand("addbulk", "Add Bulk Keys Shortcut"),
        types.BotCommand("delete", "Delete Key Options"),
        types.BotCommand("sold", "View Sold Keys"),
        types.BotCommand("livechat", "View Active Live Chats")
    ]

    try:
        bot.set_my_commands(commands)
    except Exception as e:
        print("Failed to set bot commands:", e)


# ============================================================
# START & SHORTCUT COMMANDS
# ============================================================

@bot.message_handler(
    commands=[
        "start",
        "generate",
        "stock",
        "addsingle",
        "addbulk",
        "delete",
        "sold",
        "livechat"
    ]
)
def handle_commands(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        bot.reply_to(
            message,
            "👋 Welcome!\n\n"
            "Aap apni koi bhi query ya message yahan send kar sakte hain, "
            "jo seedha Admin tak pahunch jayegi."
        )
        return

    cmd = message.text.split()[0].lower()

    if user_id in user_states:
        del user_states[user_id]

    if cmd == "/start":

        welcome_text = (
            "👑 *SUPER ADMIN CONTROL PANEL*\n\n"
            "Niche diye gaye options select karein:"
        )

        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(),
        )

    elif cmd == "/generate":
        handle_generate_key_menu_direct(message)

    elif cmd == "/stock":
        handle_all_key_stock_direct(message)

    elif cmd == "/addsingle":
        handle_add_single_menu_direct(message)

    elif cmd == "/addbulk":
        handle_add_bulk_menu_direct(message)

    elif cmd == "/delete":
        handle_delete_key_menu_direct(message)

    elif cmd == "/sold":
        handle_show_sold_key_direct(message)

    elif cmd == "/livechat":
        handle_live_chat_menu_direct(message)


# ============================================================
# BACK BUTTON
# ============================================================

@bot.message_handler(func=lambda message: message.text == "🔚 BACK")
def handle_back_button(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    if user_id in user_states:

        msg_id = user_states[user_id].get("response_msg_id")

        if msg_id:
            try:
                bot.delete_message(
                    message.chat.id,
                    msg_id
                )
            except Exception:
                pass

        del user_states[user_id]

    try:
        bot.delete_message(
            message.chat.id,
            message.message_id
        )
    except Exception:
        pass

    bot.send_message(
        message.chat.id,
        "👑 *SUPER ADMIN CONTROL PANEL*\n\n"
        "Niche diye gaye options select karein:",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )


# ============================================================
# BOTTOM MENU LISTENERS
# ============================================================

@bot.message_handler(func=lambda message: message.text == "🔑 GENERATE KEY")
def handle_gen_key_msg(message):
    handle_generate_key_menu_direct(message)


@bot.message_handler(func=lambda message: message.text == "📊 CHECK STOCK")
def handle_check_stock_msg(message):
    handle_all_key_stock_direct(message)


@bot.message_handler(func=lambda message: message.text == "➕ ADD SINGLE")
def handle_add_single_msg(message):
    handle_add_single_menu_direct(message)


@bot.message_handler(func=lambda message: message.text == "📦 ADD BULK")
def handle_add_bulk_msg(message):
    handle_add_bulk_menu_direct(message)


@bot.message_handler(func=lambda message: message.text == "🗑️ DELETE KEY")
def handle_del_key_msg(message):
    handle_delete_key_menu_direct(message)


@bot.message_handler(func=lambda message: message.text == "📋 SHOW SOLD KEY")
def handle_sold_key_msg(message):
    handle_show_sold_key_direct(message)


@bot.message_handler(func=lambda message: message.text == "💬 LIVE CHAT")
def handle_live_chat_msg(message):
    handle_live_chat_menu_direct(message)


# ============================================================
# LIVE CHAT MENU DISPLAY
# ============================================================

def handle_live_chat_menu_direct(message):
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    pipeline = [
        {"$sort": {"timestamp": -1}},
        {
            "$group": {
                "_id": "$device_id",
                "last_message": {"$first": "$message"},
                "sender": {"$first": "$sender"},
                "timestamp": {"$first": "$timestamp"}
            }
        },
        {"$sort": {"timestamp": -1}},
        {"$limit": 15}
    ]

    try:
        active_devices = list(chats_collection.aggregate(pipeline))
    except Exception:
        active_devices = []

    if not active_devices:
        sent_msg = bot.send_message(
            message.chat.id,
            "💬 *LIVE CHAT*\n\n❌ Abhi tak koi active chat available nahi hai.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )
        user_states[user_id] = {"response_msg_id": sent_msg.message_id}
        return

    text = "💬 *ACTIVE LIVE CHATS (Recent Devices):*\n\n"
    for dev in active_devices:
        device_id = dev["_id"]
        last_msg = dev.get("last_message", "")
        sender = dev.get("sender", "user")
        text += (
            f"📱 Device: `{device_id}`\n"
            f"👤 Last Sender: `{sender}`\n"
            f"📝 Msg: {last_msg}\n\n"
        )

    text += "*(Kisi bhi chat message ya notification par **Reply** karke seedha baat karein)*"

    sent_msg = bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard()
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


# ============================================================
# USER SUPPORT
# ============================================================

@bot.message_handler(func=lambda message: message.from_user.id != ADMIN_ID)
def handle_user_messages(message):

    user_id = message.from_user.id
    user_name = message.from_user.first_name or "User"
    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "No Username"
    )

    admin_msg = (
        f"💬 *NEW MESSAGE FROM USER*\n\n"
        f"👤 *Name:* {user_name}\n"
        f"🔗 *Username:* {username}\n"
        f"🆔 *User ID:* `{user_id}`\n\n"
        f"📝 *Message:*\n{message.text}"
    )

    try:

        bot.send_message(
            ADMIN_ID,
            admin_msg,
            parse_mode="Markdown"
        )

        bot.reply_to(
            message,
            "✅ Aapka message admin ko bhej diya gaya hai. "
            "Jald hi aapko reply milega!"
        )

    except Exception as e:

        print(
            f"Error forwarding message to admin: {e}"
        )

        bot.reply_to(
            message,
            "❌ Message send karne mein error aayi. "
            "Kripya baad mein try karein."
        )


# ============================================================
# ADMIN REPLY
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.reply_to_message
)
def handle_admin_reply_to_user(message):

    reply_text = (
        message.reply_to_message.text
        or message.reply_to_message.caption
    )

    if not reply_text:
        return

    if "NEW MESSAGE FROM USER" in reply_text:

        match = re.search(
            r"User\s*ID[^\d]*(\d+)",
            reply_text,
            re.IGNORECASE
        )

        if match:

            target_user_id = int(match.group(1))
            admin_reply = message.text

            try:

                bot.send_message(
                    target_user_id,
                    f"💬 *Message from Admin:*\n\n{admin_reply}",
                    parse_mode="Markdown"
                )

                bot.reply_to(
                    message,
                    "✅ Reply successfully user ko bhej diya gaya hai!",
                    reply_markup=get_main_reply_keyboard()
                )

            except Exception as e:

                bot.reply_to(
                    message,
                    f"❌ User ko message bhejne mein error aayi: {e}",
                    reply_markup=get_main_reply_keyboard()
                )

        else:

            bot.reply_to(
                message,
                "❌ Is message se User ID detect nahi ho payi.",
                reply_markup=get_main_reply_keyboard()
            )

    elif (
        "NEW CHAT FROM APP" in reply_text
        or "Media from Device" in reply_text
        or "ACTIVE LIVE CHATS" in reply_text
    ):

        match = (
            re.search(
                r"Device\s*ID[^\w]*([a-zA-Z0-9_.-]+)",
                reply_text,
                re.IGNORECASE
            )
            or
            re.search(
                r"Device[^\w]*([a-zA-Z0-9_.-]+)",
                reply_text,
                re.IGNORECASE
            )
        )

        if match:

            device_id = match.group(1)
            admin_reply = message.text

            chats_collection.insert_one({
                "device_id": device_id,
                "sender": "admin",
                "message": admin_reply,
                "media_url": "",
                "timestamp": time.time()
            })

            broadcast_message(
                device_id,
                {
                    "sender": "admin",
                    "message": admin_reply,
                    "media_url": ""
                }
            )

            try:

                bot.reply_to(
                    message,
                    f"✅ App chat reply successfully delivered instantly "
                    f"to device: `{device_id}`",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard()
                )

            except Exception as e:

                bot.reply_to(
                    message,
                    f"❌ Error: {e}",
                    reply_markup=get_main_reply_keyboard()
                )

        else:

            bot.reply_to(
                message,
                "❌ Is message se Device ID detect nahi ho payi.",
                reply_markup=get_main_reply_keyboard()
            )


# ============================================================
# 1. GENERATE KEY
# ============================================================

def handle_generate_key_menu_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:

        cb_val = d.replace(" ", "_")

        stock_count = keys_collection.count_documents({
            "duration": d,
            "status": "unused"
        })

        markup.add(
            types.InlineKeyboardButton(
                f"{d} (Stock: {stock_count})",
                callback_data=f"gen_dur_{cb_val}"
            )
        )

    sent_msg = bot.send_message(
        message.chat.id,
        "🔑 *GENERATE KEY*\n\n"
        "Duration select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("gen_dur_")
)
def callback_generate_key_duration(call):

    if call.from_user.id != ADMIN_ID:

        bot.answer_callback_query(
            call.id,
            "❌ Unauthorized!",
            show_alert=True
        )

        return

    duration = (
        call.data
        .replace("gen_dur_", "")
        .replace("_", " ")
    )

    stock_count = keys_collection.count_documents({
        "duration": duration,
        "status": "unused"
    })

    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(
        types.InlineKeyboardButton(
            f"📥 Get Key ({duration})",
            callback_data=(
                f"get_key_"
                f"{call.data.replace('gen_dur_', '')}"
            )
        )
    )

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        f"🔑 *Duration Selected:* `{duration}`\n"
        f"📦 *Available Stock:* `{stock_count}`\n\n"
        f"Niche diye gaye button par click karke key prapt karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("get_key_")
)
def callback_get_key_final(call):

    if call.from_user.id != ADMIN_ID:

        bot.answer_callback_query(
            call.id,
            "❌ Unauthorized!",
            show_alert=True
        )

        return

    duration = (
        call.data
        .replace("get_key_", "")
        .replace("_", " ")
    )

    user_id = call.from_user.id

    key_row = keys_collection.find_one(
        {
            "duration": duration,
            "status": "unused"
        },
        {
            "id": 1,
            "license_key": 1
        }
    )

    if not key_row:

        bot.answer_callback_query(
            call.id,
            f"❌ {duration} ki koi key available nahi hai!",
            show_alert=True
        )

        return

    key_id = key_row["id"]
    license_key = key_row["license_key"]

    assigned_key = keys_collection.find_one_and_update(
        {
            "id": key_id,
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

    if not assigned_key:

        bot.answer_callback_query(
            call.id,
            "❌ Key pehle hi assign ho chuki hai, dubara try karein.",
            show_alert=True
        )

        return

    bot.answer_callback_query(
        call.id,
        "Key Generated Successfully!"
    )

    bot.send_message(
        call.message.chat.id,
        f"✅ *KEY GENERATED SUCCESSFULLY!*\n\n"
        f"• *Duration:* {duration}\n"
        f"• *License Key:* `{license_key}`",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard()
    )


# ============================================================
# 2. STOCK
# ============================================================

def handle_all_key_stock_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    text = "📊 *AVAILABLE KEY STOCK SUMMARY:*\n\n"

    for d in durations:

        unused_count = keys_collection.count_documents({
            "duration": d,
            "status": "unused"
        })

        text += (
            f"• *{d}:* "
            f"`{unused_count}` keys available\n"
        )

    total_unused = keys_collection.count_documents({
        "status": "unused"
    })

    total_used = keys_collection.count_documents({
        "status": "used"
    })

    text += (
        f"\n🟢 *Total Unused Stock:* `{total_unused}`\n"
        f"🔴 *Total Used Keys:* `{total_used}`"
    )

    sent_msg = bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


# ============================================================
# 3. ADD SINGLE
# ============================================================

def handle_add_single_menu_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:

        cb_val = d.replace(" ", "_")

        markup.add(
            types.InlineKeyboardButton(
                f"➕ Add Single ({d})",
                callback_data=f"add_single_dur_{cb_val}"
            )
        )

    sent_msg = bot.send_message(
        message.chat.id,
        "➕ *ADD SINGLE KEY*\n\n"
        "Duration select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("add_single_dur_")
)
def callback_add_single_dur(call):

    if call.from_user.id != ADMIN_ID:
        return

    duration = (
        call.data
        .replace("add_single_dur_", "")
        .replace("_", " ")
    )

    user_id = call.from_user.id

    user_states[user_id] = {
        "type": "waiting_add_single_key",
        "duration": duration,
        "response_msg_id": call.message.message_id
    }

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        f"💬 Selected Duration: *{duration}*\n\n"
        f"Ab apni **License Key** yahan send karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ============================================================
# 4. ADD BULK
# ============================================================

def handle_add_bulk_menu_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:

        cb_val = d.replace(" ", "_")

        markup.add(
            types.InlineKeyboardButton(
                f"📦 Add Bulk ({d})",
                callback_data=f"add_bulk_dur_{cb_val}"
            )
        )

    sent_msg = bot.send_message(
        message.chat.id,
        "📦 *ADD BULK KEYS*\n\n"
        "Duration select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("add_bulk_dur_")
)
def callback_add_bulk_dur(call):

    if call.from_user.id != ADMIN_ID:
        return

    duration = (
        call.data
        .replace("add_bulk_dur_", "")
        .replace("_", " ")
    )

    user_id = call.from_user.id

    user_states[user_id] = {
        "type": "waiting_add_bulk_keys",
        "duration": duration,
        "response_msg_id": call.message.message_id
    }

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        f"💬 Selected Duration: *{duration}*\n\n"
        f"Ab multiple keys **ek line mein ek key** karke yahan send/paste karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown"
    )


# ============================================================
# 5. DELETE KEY
# ============================================================

def handle_delete_key_menu_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(
        types.InlineKeyboardButton(
            "🗑️ Single Delete",
            callback_data="del_single_menu"
        ),
        types.InlineKeyboardButton(
            "🗑️ Delete Sold Keys",
            callback_data="del_sold_menu_main"
        ),
        types.InlineKeyboardButton(
            "🗑️ Delete All",
            callback_data="del_all_menu_main"
        ),
    )

    sent_msg = bot.send_message(
        message.chat.id,
        "🗑️ *DELETE STOCK OPTIONS*\n\n"
        "Niche diye gaye options mein se select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


@bot.callback_query_handler(
    func=lambda call: call.data in [
        "del_single_menu",
        "del_sold_menu_main",
        "del_all_menu_main"
    ]
)
def callback_delete_submenus(call):

    if call.from_user.id != ADMIN_ID:
        return

    user_id = call.from_user.id
    data = call.data

    if data == "del_single_menu":

        bot.answer_callback_query(call.id)

        user_states[user_id] = {
            "type": "waiting_del_single"
        }

        bot.send_message(
            call.message.chat.id,
            "💬 Jis key ko delete karna hai uska "
            "**Key ID** ya **License Key** yahan send karein:",
            parse_mode="Markdown"
        )

    elif data == "del_sold_menu_main":

        bot.answer_callback_query(call.id)

        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(
            types.InlineKeyboardButton(
                "⏱️ Delete Sold Keys by Duration",
                callback_data="del_sold_by_duration_menu"
            ),
            types.InlineKeyboardButton(
                "🔥 Delete All Sold Keys",
                callback_data="conf_del_sold_ALL"
            ),
            types.InlineKeyboardButton(
                "🔙 Back",
                callback_data="del_main_menu_back"
            )
        )

        bot.edit_message_text(
            "🗑️️ *DELETE SOLD KEYS OPTIONS*\n\n"
            "Aap kis tarah ki sold keys delete karna chahte hain select karein:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif data == "del_all_menu_main":

        bot.answer_callback_query(call.id)

        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(
            types.InlineKeyboardButton(
                "⏱ Delete Key by Duration",
                callback_data="del_by_duration_menu"
            ),
            types.InlineKeyboardButton(
                "🔥 Delete All Duration Keys",
                callback_data="del_dur_prompt_ALL"
            ),
            types.InlineKeyboardButton(
                "🔙 Back",
                callback_data="del_main_menu_back"
            ),
            types.InlineKeyboardButton(
                "❌ Cancel",
                callback_data="cancel_del_all"
            )
        )

        bot.edit_message_text(
            "🗑️ *DELETE ALL OPTIONS*\n\n"
            "Aap kya delete karna chahte hain select karein:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "del_main_menu_back"
)
def callback_del_main_menu_back(call):

    if call.from_user.id != ADMIN_ID:
        return

    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(
        types.InlineKeyboardButton(
            "🗑️ Single Delete",
            callback_data="del_single_menu"
        ),
        types.InlineKeyboardButton(
            "🗑️ Delete Sold Keys",
            callback_data="del_sold_menu_main"
        ),
        types.InlineKeyboardButton(
            "🗑 Delete All",
            callback_data="del_all_menu_main"
        ),
    )

    bot.edit_message_text(
        "🗑️ *DELETE STOCK OPTIONS*\n\n"
        "Niche diye gaye options mein se select karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "del_sold_by_duration_menu"
)
def callback_del_sold_by_duration_menu(call):

    if call.from_user.id != ADMIN_ID:
        return

    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:

        cb_val = d.replace(" ", "_")

        markup.add(
            types.InlineKeyboardButton(
                f"🗑 Sold {d}",
                callback_data=f"conf_del_sold_{cb_val}"
            )
        )

    markup.add(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="del_sold_menu_main"
        )
    )

    bot.edit_message_text(
        "⏱️ *DELETE SOLD KEYS BY DURATION*\n\n"
        "Kis duration ki sold keys delete karni hain select karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "del_by_duration_menu"
)
def callback_del_by_duration_menu(call):

    if call.from_user.id != ADMIN_ID:
        return

    bot.answer_callback_query(call.id)

    markup = types.InlineKeyboardMarkup(row_width=2)

    durations = [
        "5 Hour",
        "1 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:

        cb_val = d.replace(" ", "_")

        markup.add(
            types.InlineKeyboardButton(
                f"🗑 {d}",
                callback_data=f"del_dur_prompt_{cb_val}"
            )
        )

    markup.add(
        types.InlineKeyboardButton(
            "🔙 Back",
            callback_data="del_all_menu_main"
        )
    )

    bot.edit_message_text(
        "⏱️ *DELETE KEY BY DURATION*\n\n"
        "Kis duration ki keys delete karni hain select karein:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("del_dur_prompt_")
        or call.data == "cancel_del_all"
)
def callback_del_dur_prompt(call):

    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "cancel_del_all":

        bot.answer_callback_query(
            call.id,
            "Cancelled."
        )

        try:
            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )
        except Exception:
            pass

        bot.send_message(
            call.message.chat.id,
            "👑 *SUPER ADMIN CONTROL PANEL*\n\n"
            "Niche diye gaye options select karein:",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(),
        )

        return

    target = call.data.replace(
        "del_dur_prompt_",
        ""
    )

    display_name = (
        "All Durations"
        if target == "ALL"
        else target.replace("_", " ")
    )

    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        types.InlineKeyboardButton(
            "✅ Yes, I am 100% Sure",
            callback_data=f"conf_del_{target}"
        ),
        types.InlineKeyboardButton(
            "❌ No, I am not Sure",
            callback_data="cancel_del_all"
        )
    )

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        f"⚠️ *WARNING:* Kya aap pakka "
        f"`{display_name}` ki saari keys delete karna chahte hain?",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("conf_del_")
)
def callback_confirm_deletion(call):

    if call.from_user.id != ADMIN_ID:
        return

    target = call.data.replace(
        "conf_del_",
        ""
    )

    if target == "ALL":

        res = keys_collection.delete_many({})

        bot.answer_callback_query(
            call.id,
            "All keys deleted successfully!",
            show_alert=True
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ Database ki saari keys "
            f"(`{res.deleted_count}` keys) successfully delete kar di gayi hain!",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )

    else:

        duration = target.replace("_", " ")

        res = keys_collection.delete_many({
            "duration": duration
        })

        bot.answer_callback_query(
            call.id,
            f"{res.deleted_count} keys deleted!",
            show_alert=True
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *{duration}* ki saari keys "
            f"(`{res.deleted_count}` keys) successfully delete kar di gayi hain!",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )


@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("conf_del_sold_")
)
def callback_confirm_sold_deletion(call):

    if call.from_user.id != ADMIN_ID:
        return

    target = call.data.replace(
        "conf_del_sold_",
        ""
    )

    if target == "ALL":

        res = keys_collection.delete_many({
            "status": "used"
        })

        bot.answer_callback_query(
            call.id,
            "All sold keys deleted successfully!",
            show_alert=True
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ Database ki saari sold/used keys "
            f"(`{res.deleted_count}` keys) successfully delete kar di gayi hain!",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )

    else:

        duration = target.replace("_", " ")

        res = keys_collection.delete_many({
            "duration": duration,
            "status": "used"
        })

        bot.answer_callback_query(
            call.id,
            f"{res.deleted_count} sold keys deleted!",
            show_alert=True
        )

        bot.send_message(
            call.message.chat.id,
            f"✅ *{duration}* ki saari sold/used keys "
            f"(`{res.deleted_count}` keys) successfully delete kar di gayi hain!",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )


# ============================================================
# 6. SHOW SOLD
# ============================================================

def handle_show_sold_key_direct(message):

    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        return

    keys = list(
        keys_collection.find(
            {
                "status": "used"
            },
            {
                "id": 1,
                "duration": 1,
                "license_key": 1,
                "assigned_to": 1
            }
        )
        .sort("id", DESCENDING)
        .limit(30)
    )

    if not keys:

        sent_msg = bot.send_message(
            message.chat.id,
            "❌ Abhi tak koi bhi key use/sold nahi hui hai.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(),
        )

        user_states[user_id] = {
            "response_msg_id": sent_msg.message_id
        }

        return

    text = "📋 *RECENT SOLD / USED KEYS (Last 30):*\n\n"

    for key in keys:

        kid = key["id"]
        dur = key.get("duration", "")
        lkey = key.get("license_key", "")
        assigned = key.get(
            "assigned_to",
            "Unknown"
        )

        text += (
            f"🆔 ID: `{kid}` | *{dur}*\n"
            f"🔑 `{lkey}`\n"
            f"👤 Assigned: `{assigned}`\n\n"
        )

    sent_msg = bot.send_message(
        message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )

    user_states[user_id] = {
        "response_msg_id": sent_msg.message_id
    }


# ============================================================
# REVOKE KEY
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("rev_key_")
)
def callback_revoke_key_from_payment(call):

    if call.from_user.id != ADMIN_ID:

        bot.answer_callback_query(
            call.id,
            "❌ Unauthorized!",
            show_alert=True
        )

        return

    try:

        key_id = int(
            call.data.replace(
                "rev_key_",
                ""
            )
        )

        result = keys_collection.delete_one({
            "id": key_id
        })

        if result.deleted_count > 0:

            bot.answer_callback_query(
                call.id,
                "Key deleted successfully!",
                show_alert=True
            )

            try:

                bot.edit_message_text(
                    call.message.text
                    + "\n\n"
                    "❌ STATUS: Key deleted/revoked by Admin.",
                    call.message.chat.id,
                    call.message.message_id
                )

            except Exception:
                pass

        else:

            bot.answer_callback_query(
                call.id,
                "❌ Key already deleted or not found.",
                show_alert=True
            )

    except Exception as e:

        bot.answer_callback_query(
            call.id,
            f"❌ Error: {e}",
            show_alert=True
        )


# ============================================================
# STATE INPUT
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.from_user.id in user_states
        and user_states[message.from_user.id].get("type")
        in [
            "waiting_add_single_key",
            "waiting_add_bulk_keys",
            "waiting_del_single"
        ]
)
def handle_user_state_input(message):

    user_id = message.from_user.id

    state = user_states[user_id]

    action_type = state["type"]

    text = (
        message.text
        or ""
    ).strip()

    if text in [
        "🔑 GENERATE KEY",
        "📊 CHECK STOCK",
        "➕ ADD SINGLE",
        "📦 ADD BULK",
        "🗑️ DELETE KEY",
        "📋 SHOW SOLD KEY",
        "💬 LIVE CHAT",
        "🔚 BACK"
    ]:
        return

    if action_type == "waiting_add_single_key":

        duration = state.get("duration")

        del user_states[user_id]

        if not text:

            bot.reply_to(
                message,
                "❌ Key empty nahi ho sakti!",
                reply_markup=get_main_reply_keyboard()
            )

            return

        try:

            new_id = get_next_id(
                "key_id"
            )

            keys_collection.insert_one({
                "id": new_id,
                "duration": duration,
                "license_key": text,
                "status": "unused",
                "assigned_to": None
            })

            bot.reply_to(
                message,
                f"✅ Single Key successfully added!\n"
                f"• Duration: {duration}\n"
                f"• Key: `{text}`",
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard()
            )

        except DuplicateKeyError:

            bot.reply_to(
                message,
                "❌ Yeh license key pehle se database mein mojood hai!",
                reply_markup=get_main_reply_keyboard()
            )

        except Exception as e:

            bot.reply_to(
                message,
                f"❌ Error: {e}",
                reply_markup=get_main_reply_keyboard()
            )

    elif action_type == "waiting_add_bulk_keys":

        duration = state.get("duration")

        del user_states[user_id]

        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

        if not lines:

            bot.reply_to(
                message,
                "❌ Koi keys nahi mili!",
                reply_markup=get_main_reply_keyboard()
            )

            return

        added_count = 0
        duplicate_count = 0

        for line in lines:

            try:

                new_id = get_next_id(
                    "key_id"
                )

                keys_collection.insert_one({
                    "id": new_id,
                    "duration": duration,
                    "license_key": line,
                    "status": "unused",
                    "assigned_to": None
                })

                added_count += 1

            except DuplicateKeyError:

                duplicate_count += 1

            except Exception:
                pass

        bot.reply_to(
            message,
            f"📦 *BULK ADD REPORT*\n\n"
            f"• *Duration:* {duration}\n"
            f"• *Successfully Added:* `{added_count}`\n"
            f"• *Duplicates (Skipped):* `{duplicate_count}`",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )

    elif action_type == "waiting_del_single":

        del user_states[user_id]

        query = text

        try:

            if query.isdigit():

                result = keys_collection.delete_one({
                    "id": int(query)
                })

            else:

                result = keys_collection.delete_one({
                    "license_key": query
                })

            if result.deleted_count > 0:

                bot.reply_to(
                    message,
                    "✅ Key successfully delete kar di gayi hai!",
                    reply_markup=get_main_reply_keyboard()
                )

            else:

                bot.reply_to(
                    message,
                    "❌ Yeh key database mein nahi mili.",
                    reply_markup=get_main_reply_keyboard()
                )

        except Exception as e:

            bot.reply_to(
                message,
                f"❌ Error: {e}",
                reply_markup=get_main_reply_keyboard()
            )


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():

    return (
        "BOT & API SERVER IS ACTIVE AND RUNNING "
        "WITH MONGODB, AUTO-PAYMENT APPROVAL & REAL-TIME CHAT SUPPORT!"
    )


# ============================================================
# FREE TASK
# ============================================================

@app.route(
    "/api/submit_free_task",
    methods=["POST"]
)
def submit_free_task():

    data = request.json or {}

    device_id = data.get(
        "device_id"
    )

    if not device_id:

        return jsonify({
            "status": "error",
            "message": "❌ Device ID missing hai!"
        }), 400

    current_time = time.time()

    cooldown_duration = 5 * 60 * 60

    cooldown_record = (
        device_cooldowns_collection.find_one({
            "device_id": device_id
        })
    )

    if cooldown_record:

        last_time = cooldown_record.get(
            "last_claimed_time",
            0
        )

        if (
            current_time - last_time
            < cooldown_duration
        ):

            remaining_seconds = int(
                cooldown_duration
                - (current_time - last_time)
            )

            hours = (
                remaining_seconds
                // 3600
            )

            mins = (
                remaining_seconds
                % 3600
                // 60
            )

            return jsonify({
                "status": "error",
                "message": (
                    f"❌ Aapko agli free key "
                    f"{hours} ghante "
                    f"{mins} minute baad milegi!"
                )
            }), 400

    key_doc = keys_collection.find_one(
        {
            "duration": "5 Hour",
            "status": "unused"
        },
        {
            "id": 1,
            "license_key": 1
        }
    )

    if not key_doc:

        return jsonify({
            "status": "error",
            "message": (
                "❌ Free key stock filhaal "
                "khatam ho gaya hai!"
            )
        }), 400

    key_id = key_doc["id"]

    license_key = key_doc[
        "license_key"
    ]

    assigned = keys_collection.find_one_and_update(
        {
            "id": key_id,
            "status": "unused"
        },
        {
            "$set": {
                "status": "used",
                "assigned_to": (
                    f"Device: {device_id}"
                )
            }
        },
        return_document=True
    )

    if not assigned:

        return jsonify({
            "status": "error",
            "message": (
                "❌ Key pehle hi assign ho chuki hai, "
                "dubara try karein."
            )
        }), 400

    device_cooldowns_collection.update_one(
        {
            "device_id": device_id
        },
        {
            "$set": {
                "last_claimed_time": current_time
            }
        },
        upsert=True
    )

    return jsonify({
        "status": "success",
        "key": license_key
    })


# ============================================================
# PAYMENT SUBMIT & AUTO-APPROVAL API
# ============================================================

@app.route(
    "/api/submit_payment",
    methods=["POST"]
)
def submit_payment():

    data = request.json or {}

    utr = str(
        data.get("utr", "")
    ).strip()

    plan_raw = str(
        data.get("plan", "")
    ).strip()

    amount = data.get(
        "amount"
    )

    device_id = str(
        data.get("device_id", "")
    ).strip()

    device_model = str(
        data.get("device_model", "")
    ).strip()

    if not utr or not plan_raw:

        return jsonify({
            "status": "error",
            "message": (
                "Invalid data, "
                "UTR and Plan required"
            )
        }), 400

    plan = normalize_plan(
        plan_raw
    )

    if not plan:

        return jsonify({
            "status": "error",
            "message": "Invalid subscription plan."
        }), 400

    existing_payment = payments_collection.find_one({"utr": utr})
    if existing_payment:
        return jsonify({
            "status": existing_payment.get("status", "approved"),
            "message": "Payment already processed",
            "key": existing_payment.get("key", "")
        })

    key_row = keys_collection.find_one(
        {
            "duration": plan,
            "status": "unused"
        },
        {
            "id": 1,
            "license_key": 1
        }
    )

    if not key_row:
        return jsonify({
            "status": "error",
            "message": "❌ Stock empty for this plan. Please contact admin."
        }), 400

    key_id = key_row["id"]
    license_key = key_row["license_key"]

    assigned_key = keys_collection.find_one_and_update(
        {
            "id": key_id,
            "status": "unused"
        },
        {
            "$set": {
                "status": "used",
                "assigned_to": f"Auto Payment | UTR: {utr}"
            }
        },
        return_document=True
    )

    if not assigned_key:
        return jsonify({
            "status": "error",
            "message": "❌ Key assignment failed, please try again."
        }), 400

    payment_id = get_next_id("payment_id")
    buy_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    payment_doc = {
        "payment_id": payment_id,
        "utr": utr,
        "plan": plan,
        "amount": amount,
        "status": "approved",
        "key": license_key,
        "key_id": key_id,
        "device_id": device_id,
        "device_model": device_model,
        "buy_time": buy_time,
        "approved_at": buy_time,
        "created_at": time.time()
    }

    try:
        payments_collection.insert_one(payment_doc)
    except DuplicateKeyError:
        keys_collection.update_one(
            {"id": key_id},
            {"$set": {"status": "unused", "assigned_to": None}}
        )
        existing = payments_collection.find_one({"utr": utr})
        return jsonify({
            "status": existing.get("status", "approved"),
            "key": existing.get("key", "")
        })

    try:
        admin_msg = (
            "🤖 *AUTOMATIC PAYMENT CONFIRMED*\n\n"
            f"🆔 *Payment ID:* `{payment_id}`\n"
            f"📦 *Plan:* `{plan}`\n"
            f"💰 *Amount:* `₹{amount}`\n"
            f"💳 *UTR:* `{utr}`\n"
            f"🕒 *Time:* `{buy_time}`\n"
            f"📱 *Device ID:* `{device_id or 'N/A'}`\n"
            f"📱 *Device Model:* `{device_model or 'N/A'}`\n\n"
            f"🔑 *Assigned Key:*\n`{license_key}`\n\n"
            "🟢 Status: *AUTO APPROVED & KEY ISSUED*"
        )
        bot.send_message(
            ADMIN_ID,
            admin_msg,
            parse_mode="Markdown"
        )
    except Exception as e:
        print("Payment admin notification error:", e)

    return jsonify({
        "status": "approved",
        "payment_id": payment_id,
        "key": license_key,
        "message": "Payment verified and key issued automatically!"
    })


# ============================================================
# CHECK PAYMENT STATUS
# ============================================================

@app.route(
    "/api/check_status/<utr>",
    methods=["GET"]
)
def check_status(utr):

    utr = str(
        utr
    ).strip()

    payment_info = (
        payments_collection.find_one({
            "utr": utr
        })
    )

    if not payment_info:

        return jsonify({
            "status": "pending",
            "key": ""
        })

    return jsonify({
        "status": payment_info.get(
            "status",
            "pending"
        ),
        "key": payment_info.get(
            "key",
            ""
        )
    })


# ============================================================
# CHAT
# ============================================================

@app.route(
    "/api/send_chat",
    methods=["POST"]
)
def send_chat():

    data = request.json or {}

    device_id = data.get(
        "device_id"
    )

    sender = data.get(
        "sender",
        "user"
    )

    message = data.get(
        "message",
        ""
    )

    media_url = data.get(
        "media_url",
        ""
    )

    if not device_id or (
        not message
        and not media_url
    ):

        return jsonify({
            "error":
                "device_id and message/media required"
        }), 400

    chat_doc = {
        "device_id": device_id,
        "sender": sender,
        "message": message,
        "media_url": media_url,
        "timestamp": time.time()
    }

    chats_collection.insert_one(
        chat_doc
    )

    broadcast_message(
        device_id,
        {
            "sender": sender,
            "message": message,
            "media_url": media_url
        }
    )

    if sender == "user":

        admin_msg = (
            "💬 *NEW CHAT FROM APP*\n\n"
            f"🆔 *Device ID:* `{device_id}`\n\n"
            f"📝 *Message:*\n{message}"
        )

        try:

            bot.send_message(
                ADMIN_ID,
                admin_msg,
                parse_mode="Markdown"
            )

        except Exception as e:

            print(
                "Error sending chat to admin:",
                e
            )

    return jsonify({
        "status": "success"
    })


# ============================================================
# MEDIA
# ============================================================

@app.route(
    "/api/send_media",
    methods=["POST"]
)
def send_media():

    try:

        device_id = request.form.get(
            "device_id"
        )

        file = request.files.get(
            "file"
        )

        if not device_id or not file:

            return jsonify({
                "error":
                    "Missing fields"
            }), 400

        file_path = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        file.save(
            file_path
        )

        media_url = (
            f"{RENDER_EXTERNAL_URL}"
            f"/{file_path}"
        )

        chat_doc = {
            "device_id": device_id,
            "sender": "user",
            "message": "[Media File]",
            "media_url": media_url,
            "timestamp": time.time()
        }

        chats_collection.insert_one(
            chat_doc
        )

        broadcast_message(
            device_id,
            {
                "sender": "user",
                "message": "[Media File]",
                "media_url": media_url
            }
        )

        try:

            with open(
                file_path,
                "rb"
            ) as f:

                bot.send_document(
                    ADMIN_ID,
                    f,
                    caption=(
                        f"📎 Media from Device: "
                        f"`{device_id}`"
                    ),
                    parse_mode="Markdown"
                )

        except Exception as e:

            print(
                "Error sending media to telegram:",
                e
            )

        return jsonify({
            "status": "success",
            "url": media_url
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# SSE STREAM
# ============================================================

@app.route(
    "/api/stream/<device_id>"
)
def stream(device_id):

    q = queue.Queue()

    with queues_lock:

        if device_id not in client_queues:

            client_queues[device_id] = []

        client_queues[
            device_id
        ].append(q)

    def event_stream():

        try:

            while True:

                msg_data = q.get()

                yield (
                    f"data: "
                    f"{msg_data}\n\n"
                )

        except GeneratorExit:

            with queues_lock:

                if (
                    device_id
                    in client_queues
                    and q
                    in client_queues[
                        device_id
                    ]
                ):

                    client_queues[
                        device_id
                    ].remove(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream"
    )


# ============================================================
# GET CHAT
# ============================================================

@app.route(
    "/api/get_chat/<device_id>",
    methods=["GET"]
)
def get_chat(device_id):

    messages = list(
        chats_collection.find(
            {
                "device_id":
                    device_id
            },
            {
                "_id": 0
            }
        )
        .sort(
            "timestamp",
            ASCENDING
        )
    )

    formatted = []

    for m in messages:

        formatted.append({
            "sender": m.get(
                "sender",
                "user"
            ),
            "message": m.get(
                "message",
                ""
            ),
            "media_url": m.get(
                "media_url",
                ""
            )
        })

    return jsonify(
        formatted
    )


# ============================================================
# FLASK START
# ============================================================

def run_flask():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# ============================================================
# START BOT & SERVER
# ============================================================

if __name__ == "__main__":

    setup_bot_commands()

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    try:

        bot.remove_webhook()

        bot.delete_webhook(
            drop_pending_updates=True
        )

    except Exception as e:

        print(
            f"Webhook cleanup error: {e}"
        )

    print(
        "Bot and Flask API Server are running "
        "with MongoDB, Auto-Payment Approval, "
        "SSE Streaming & Live Chat Support..."
    )

    bot.infinity_polling(
        timeout=60,
        long_polling_timeout=60
    )
