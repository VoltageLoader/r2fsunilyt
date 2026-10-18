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

    orders_collection.create_index(
        [("user_id", ASCENDING)]
    )

    loaders_collection.create_index(
        [("loader_key", ASCENDING)],
        unique=True,
        name="unique_loader_key",
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
# USER STATE
# ============================================================

user_states = {}
admin_reply_map = {}


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
                    reply_markup=get_main_reply_keyboard(user_id),
                )
            except Exception:
                pass

    except Exception as e:
        print(f"TIMEOUT WORKER ERROR: {e}")


# ============================================================
# KEYBOARDS
# ============================================================

def get_main_reply_keyboard(user_id=None):
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
            types.KeyboardButton("🔑 GENERATE KEY"),
            types.KeyboardButton("👑 SUPER ADMIN")
        )

    markup.add(
        types.KeyboardButton("♻️ APK & SETUP"),
        types.KeyboardButton("💬 CONTACT SUPPORT")
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

    if user_id in user_states:
        del user_states[user_id]

    welcome_text = (
        "💎 *WELCOME TO R2F OFFICIAL PREMIUM STORE* ✅\n\n"
        "✨ *SAFE, FAST & SECURE SERVICES* 🛡️\n\n"
        "👉 *CLICK THE MENU BUTTONS BELOW:* 👇"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(user_id),
    )


# ============================================================
# BACK BUTTON
# ============================================================

@bot.message_handler(func=lambda message: message.text == "🔚 BACK")
def handle_back_button(message):
    user_id = message.from_user.id

    if user_id in user_states:
        if "qr_msg_id" in user_states[user_id]:
            try:
                bot.delete_message(
                    message.chat.id,
                    user_states[user_id]["qr_msg_id"]
                )
            except Exception:
                pass
        del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "🏠 *MAIN MENU:* ✅",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(user_id),
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

    durations = [
        "5 Hour",
        "1 Day",
        "2 Day",
        "3 Day",
        "7 Day",
        "30 Day"
    ]

    for d in durations:
        cb_val = d.replace(" ", "_")
        markup.add(
            types.InlineKeyboardButton(
                f"⏱ {d.upper()}",
                callback_data=f"genkey_{cb_val}"
            )
        )

    bot.send_message(
        message.chat.id,
        "🔑 *GENERATE KEY* ✅\n\n"
        "DURATION SELECT KAREIN:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("genkey_"))
def handle_genkey_callback(call):
    user_id = call.from_user.id

    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ UNAUTHORIZED!", show_alert=True)
        return

    duration = call.data.replace("genkey_", "").replace("_", " ")
    bot.answer_callback_query(call.id)

    key_row = keys_collection.find_one_and_update(
        {
            "duration": duration,
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
        bot.send_message(
            call.message.chat.id,
            f"❌ *OUT OF STOCK!*\n"
            f"DURATION *{duration}* KE LIYE KOI UNUSED KEY AVAILABLE NAHI HAI.",
            parse_mode="Markdown"
        )
        return

    kid = key_row["id"]
    license_key = key_row["license_key"]

    bot.send_message(
        call.message.chat.id,
        f"✅ *KEY GENERATED SUCCESSFULLY!* ✅\n\n"
        f"• *ID:* `{kid}`\n"
        f"• *DURATION:* {duration} ✨\n"
        f"• *KEY:* `{license_key}` 💎",
        parse_mode="Markdown",
    )


# ============================================================
# SUPER ADMIN PANEL
# ============================================================

@bot.message_handler(func=lambda message: message.text == "👑 SUPER ADMIN")
def super_admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ YOU ARE NOT AUTHORIZED!")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ ADD LOADER (UPLOAD APK)", callback_data="sa_add_loader_menu"),
        types.InlineKeyboardButton("📺 ADD SETUP VIDEO LINK", callback_data="sa_add_video_menu"),
        types.InlineKeyboardButton("➕ ADD SINGLE KEY", callback_data="sa_add_single"),
        types.InlineKeyboardButton("📦 ADD BULK KEY", callback_data="sa_add_bulk"),
        types.InlineKeyboardButton("❌ DELETE SINGLE KEY", callback_data="sa_del_single"),
        types.InlineKeyboardButton("🗑️ DELETE BULK KEYS", callback_data="sa_del_bulk"),
        types.InlineKeyboardButton("📋 SHOW ALL KEYS", callback_data="sa_show_keys"),
    )

    bot.send_message(
        message.chat.id,
        "👑 *SUPER ADMIN PANEL* ✅\n\n"
        "NICHE DIYE GAYE OPTIONS MEIN SE SELECT KAREIN:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ============================================================
# SUPER ADMIN CALLBACKS
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("sa_"))
def super_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ UNAUTHORIZED!", show_alert=True)
        return

    data = call.data

    if data == "sa_add_loader_menu":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚙️ VOLTAGE LOADER", callback_data="sa_ldr_voltage_loader"),
            types.InlineKeyboardButton("🚀 VIP LOADER", callback_data="sa_ldr_vip_loader"),
            types.InlineKeyboardButton("💎 NICE X NEXA", callback_data="sa_ldr_nicexnexa"),
            types.InlineKeyboardButton("⚡ NICE X NEXA SERVER", callback_data="sa_ldr_nicexnexaserver"),
        )
        bot.edit_message_text(
            "📂 *ADD LOADER (UPLOAD APK)* ✅\n\nKIS LOADER KE LIYE APK UPLOAD KARI HAI SELECT KAREIN:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data == "sa_add_video_menu":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚙️ VOLTAGE LOADER", callback_data="sa_vldr_voltage_loader"),
            types.InlineKeyboardButton("🚀 VIP LOADER", callback_data="sa_vldr_vip_loader"),
            types.InlineKeyboardButton("💎 NICE X NEXA", callback_data="sa_vldr_nicexnexa"),
            types.InlineKeyboardButton("⚡ NICE X NEXA SERVER", callback_data="sa_vldr_nicexnexaserver"),
        )
        bot.edit_message_text(
            "📺 *ADD SETUP VIDEO LINK* ✅\n\nKIS LOADER KE LIYE SETUP VIDEO LINK ADD KARNA HAI SELECT KAREIN:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data.startswith("sa_ldr_"):
        loader_key = data.replace("sa_ldr_", "")
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_loader_apk", "loader_key": loader_key}
        bot.send_message(
            call.message.chat.id,
            f"📂 *UPLOAD APK FOR {loader_key.upper().replace('_', ' ')}* ✅\n\n"
            "💬 AB APNI **APK FILE (.apk)** YAHAN CHAT MEIN SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data.startswith("sa_vldr_"):
        loader_key = data.replace("sa_vldr_", "")
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_loader_video", "loader_key": loader_key}
        bot.send_message(
            call.message.chat.id,
            f"📺 *ADD SETUP VIDEO LINK FOR {loader_key.upper().replace('_', ' ')}* ✅\n\n"
            "💬 AB APNA **SETUP VIDEO LINK** (JAISE: `https://t.me/VoltageLoader`) YAHAN SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data == "sa_add_single":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        durations = ["5 Hour", "1 Day", "2 Day", "3 Day", "7 Day", "30 Day"]
        for d in durations:
            cb_val = d.replace(" ", "_")
            markup.add(types.InlineKeyboardButton(f"⏱ {d.upper()}", callback_data=f"sa_sdur_{cb_val}"))

        bot.edit_message_text(
            "➕ *ADD SINGLE KEY* ✅\n\nDURATION SELECT KAREIN:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data.startswith("sa_sdur_"):
        duration = data.replace("sa_sdur_", "").replace("_", " ")
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_single_key", "duration": duration}
        bot.send_message(
            call.message.chat.id,
            f"➕ *ADD SINGLE KEY* ✅\n\nDURATION: *{duration}*\n\n💬 AB APNI **LICENSE KEY** YAHAN CHAT MEIN SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data == "sa_add_bulk":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        durations = ["5 Hour", "1 Day", "2 Day", "3 Day", "7 Day", "30 Day"]
        for d in durations:
            cb_val = d.replace(" ", "_")
            markup.add(types.InlineKeyboardButton(f"⏱ {d.upper()}", callback_data=f"sa_bdur_{cb_val}"))

        bot.edit_message_text(
            "📦 *ADD BULK KEYS* ✅\n\nDURATION SELECT KAREIN:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data.startswith("sa_bdur_"):
        duration = data.replace("sa_bdur_", "").replace("_", " ")
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_bulk_keys", "duration": duration}
        bot.send_message(
            call.message.chat.id,
            f"📦 *ADD BULK KEYS* ✅\n\nDURATION: *{duration}*\n\n💬 MULTIPLE KEYS **EK LINE MEIN EK KEY** KARKE YAHAN PASTE/SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data == "sa_del_single":
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_del_id"}
        bot.send_message(
            call.message.chat.id,
            "❌ *DELETE SINGLE KEY* ✅\n\n💬 JIS KEY KO DELETE KARNA HAI USKA **KEY ID** YAHAN SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data == "sa_del_bulk":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📋 PASTE KEYS TO DELETE IN BULK", callback_data="sa_del_paste_bulk"),
            types.InlineKeyboardButton("🗑️ DELETE ALL UNUSED KEYS", callback_data="sa_del_all_unused"),
        )
        bot.edit_message_text(
            "🗑️ *DELETE BULK OPTIONS* ✅\n\nOPTION SELECT KAREIN:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data == "sa_del_paste_bulk":
        bot.answer_callback_query(call.id)
        user_states[ADMIN_ID] = {"type": "waiting_bulk_del"}
        bot.send_message(
            call.message.chat.id,
            "🗑 *DELETE BULK KEYS BY LIST* ✅\n\n💬 JIN KEYS KO DELETE KARNA HAI UNHE **EK LINE MEIN EK KEY** KARKE YAHAN SEND KAREIN:",
            parse_mode="Markdown",
        )

    elif data == "sa_del_all_unused":
        bot.answer_callback_query(call.id)
        result = keys_collection.delete_many({"status": "unused"})
        bot.send_message(
            call.message.chat.id,
            f"✅ SAARI UNUSED KEYS SUCCESSFULLY DELETE KAR DI GAYI HAIN! ✅\n\nTOTAL DELETED: `{result.deleted_count}`",
            parse_mode="Markdown",
        )

    elif data == "sa_show_keys":
        bot.answer_callback_query(call.id)
        keys = list(keys_collection.find({}, {"id": 1, "duration": 1, "license_key": 1, "status": 1, "assigned_to": 1}).sort("id", DESCENDING).limit(50))
        if not keys:
            bot.send_message(call.message.chat.id, "❌ DATABASE MEIN KOI KEYS AVAILABLE NAHI HAIN.")
            return

        text = "📋 *ALL STORED KEYS (LAST 50):* ✅\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        for key in keys:
            kid = key["id"]
            duration = key.get("duration", "")
            license_key = key.get("license_key", "")
            status = key.get("status", "unused")
            assigned_to = key.get("assigned_to")

            status_icon = "🟢 UNUSED" if status == "unused" else f"🔴 USED (USER: {assigned_to})"
            text += f"🆔 ID: `{kid}` | *{duration}*\n🔑 `{license_key}`\nSTATUS: {status_icon}\n\n"
            markup.add(types.InlineKeyboardButton(f"🗑️ DELETE ID {kid}", callback_data=f"sa_del_id_{kid}"))

        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("sa_del_id_"):
        kid = int(data.split("_")[3])
        result = keys_collection.delete_one({"id": kid})
        bot.answer_callback_query(call.id, f"✅ KEY ID {kid} DELETED SUCCESSFULLY!", show_alert=True)
        try:
            if result.deleted_count:
                bot.edit_message_text(f"✅ *KEY ID `{kid}` SUCCESSFULLY DELETED!* ✅", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            else:
                bot.edit_message_text(f"❌ *KEY ID `{kid}` NOT FOUND!*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except Exception:
            pass


# ============================================================
# ADMIN STATE INPUT (KEYS, LOADER APK & VIDEO LINK)
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.from_user.id in user_states
        and user_states[message.from_user.id]["type"]
        in ["waiting_single_key", "waiting_bulk_keys", "waiting_del_id", "waiting_bulk_del", "waiting_loader_apk", "waiting_loader_video"],
    content_types=["text", "document"]
)
def handle_admin_state_input(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    action_type = state["type"]

    if action_type == "waiting_loader_apk":
        loader_key = state["loader_key"]
        if not message.document:
            bot.reply_to(message, "❌ KRIPYA EK VALID APK DOCUMENT FILE SEND KAREIN!")
            return

        file_id = message.document.file_id
        file_name = message.document.file_name or "app.apk"

        loaders_collection.update_one(
            {"loader_key": loader_key},
            {"$set": {"file_id": file_id, "file_name": file_name}},
            upsert=True
        )

        del user_states[user_id]
        bot.reply_to(
            message,
            f"✅ *APK SUCCESSFULLY SAVED FOR {loader_key.upper().replace('_', ' ')}!* ✅\n\n"
            f"• *File Name:* `{file_name}`\n"
            f"Ab koi bhi user APK & SETUP se ise instant download kar sakega.",
            parse_mode="Markdown"
        )
        return

    if action_type == "waiting_loader_video":
        loader_key = state["loader_key"]
        video_link = (message.text or "").strip()

        if not video_link:
            bot.reply_to(message, "❌ KRIPYA VALID VIDEO LINK SEND KAREIN!")
            return

        loaders_collection.update_one(
            {"loader_key": loader_key},
            {"$set": {"video_link": video_link}},
            upsert=True
        )

        del user_states[user_id]
        bot.reply_to(
            message,
            f"✅ *SETUP VIDEO LINK SUCCESSFULLY SAVED FOR {loader_key.upper().replace('_', ' ')}!* ✅\n\n"
            f"• *Link:* `{video_link}`",
            parse_mode="Markdown"
        )
        return

    text = (message.text or "").strip()

    if text.startswith("/") or text in [
        "🛒 PURCHASE KEY",
        "🔐 MY KEYS",
        "🔑 GENERATE KEY",
        "♻️ APK & SETUP",
        "💬 CONTACT SUPPORT",
        "🔚 BACK",
        "👑 SUPER ADMIN",
    ]:
        del user_states[user_id]
        if text == "👑 SUPER ADMIN":
            super_admin_panel(message)
        elif text == "🔑 GENERATE KEY":
            handle_gen_key_menu(message)
        elif text == "🔚 BACK":
            handle_back_button(message)
        else:
            handle_reply_menu(message)
        return

    if action_type == "waiting_single_key":
        duration = state["duration"]
        try:
            new_id = get_next_id("keys")
            keys_collection.insert_one({"id": new_id, "duration": duration, "license_key": text, "status": "unused", "assigned_to": None})
            del user_states[user_id]
            bot.reply_to(message, f"✅ *SINGLE KEY ADDED SUCCESSFULLY!* ✅\n\n• *DURATION:* {duration}\n• *KEY:* `{text}`", parse_mode="Markdown")
        except DuplicateKeyError:
            bot.reply_to(message, "❌ *DUPLICATE KEY ERROR!*\nYEH LICENSE KEY PEHLE SE DATABASE MEIN MOJOOD HAI.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, "❌ KEY ADD KARTE WAQT DATABASE ERROR AA GAYA.")

    elif action_type == "waiting_bulk_keys":
        duration = state["duration"]
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            bot.reply_to(message, "❌ KOI KEYS NAHI MILI!")
            return

        added_count, duplicate_count = 0, 0
        for key in lines:
            try:
                new_id = get_next_id("keys")
                keys_collection.insert_one({"id": new_id, "duration": duration, "license_key": key, "status": "unused", "assigned_to": None})
                added_count += 1
            except DuplicateKeyError:
                duplicate_count += 1

        del user_states[user_id]
        bot.reply_to(message, f"📦 *BULK KEYS ADDED REPORT* ✅\n\n• *DURATION:* {duration}\n• *SUCCESSFULLY ADDED:* `{added_count}`\n• *DUPLICATES SKIPPED:* `{duplicate_count}`", parse_mode="Markdown")

    elif action_type == "waiting_del_id":
        try:
            key_id = int(text)
            result = keys_collection.delete_one({"id": key_id})
            del user_states[user_id]
            if result.deleted_count:
                bot.reply_to(message, f"✅ KEY ID `{key_id}` SUCCESSFULLY DELETE KAR DI GAYI HAI! ✅", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"❌ KEY ID `{key_id}` NAHI MILI.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ SAHI KEY ID ENTER KAREIN (SIRF NUMBER HONA CHAHIYE).", parse_mode="Markdown")

    elif action_type == "waiting_bulk_del":
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            bot.reply_to(message, "❌ KOI KEYS NAHI MILI!")
            return

        deleted_count = 0
        for key in lines:
            result = keys_collection.delete_one({"license_key": key})
            deleted_count += result.deleted_count

        del user_states[user_id]
        bot.reply_to(message, f"🗑️ *BULK DELETE REPORT* ✅\n\n• *TOTAL KEYS DELETED:* `{deleted_count}`", parse_mode="Markdown")


# ============================================================
# REPLY MENU
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.text in [
            "🛒 PURCHASE KEY",
            "🔐 MY KEYS",
            "♻️ APK & SETUP",
            "💬 CONTACT SUPPORT",
        ]
)
def handle_reply_menu(message):
    user_id = message.from_user.id

    if user_id in user_states:
        del user_states[user_id]

    if message.text == "🛒 PURCHASE KEY":
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
            stock_count = keys_collection.count_documents({"duration": duration, "status": "unused"})
            button_title = f"{title} | STOCK: {stock_count}"
            cb_duration = duration.replace(" ", "_")
            markup.add(types.InlineKeyboardButton(button_title, callback_data=f"plan_{cb_duration}_{amount}"))

        bot.send_message(
            message.chat.id,
            "📋 *SELECT PLAN* ✅\n\nAPNA PLAN SELECT KAREIN:",
            parse_mode="Markdown",
            reply_markup=markup,
        )

        bot.send_message(
            message.chat.id,
            "👇 *BACK:*",
            parse_mode="Markdown",
            reply_markup=get_back_reply_keyboard(),
        )

    elif message.text == "🔐 MY KEYS":
        keys = list(keys_collection.find({"status": "used", "assigned_to": user_id}, {"id": 1, "duration": 1, "license_key": 1}).sort("id", DESCENDING))
        if not keys:
            bot.send_message(message.chat.id, "❌ AAPKE PAAS KOI ACTIVE KEY NAHI HAI!", parse_mode="Markdown")
            return

        for key in keys:
            key_id = key["id"]
            duration = key["duration"]
            license_key = key["license_key"]

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🔄 RESET", callback_data=f"reset_{key_id}"),
                types.InlineKeyboardButton("🗑 DELETE", callback_data=f"delmykey_{key_id}"),
            )

            bot.send_message(
                message.chat.id,
                f"💎 *ACTIVE PLAN:* ({duration}) ✅\n🔑 `{license_key}`",
                parse_mode="Markdown",
                reply_markup=markup
            )

    elif message.text == "♻️ APK & SETUP":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚙️ VOLTAGE LOADER", callback_data="setup_voltage_loader"),
            types.InlineKeyboardButton("🚀 VIP LOADER", callback_data="setup_vip_loader"),
            types.InlineKeyboardButton("💎 NICE X NEXA", callback_data="setup_nicexnexa"),
            types.InlineKeyboardButton("⚡ NICE X NEXA SERVER", callback_data="setup_nicexnexaserver"),
        )
        bot.send_message(
            message.chat.id,
            "♻ *SELECT LOADER/SERVER FOR SETUP & APK:* ✅",
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif message.text == "💬 CONTACT SUPPORT":
        user_states[user_id] = {"type": "support"}
        bot.send_message(
            message.chat.id,
            "💬 *WELCOME TO SUPPORT CHAT!* ✅\n\n"
            "APNA MESSAGE YAHAN SEND KAREIN, ADMIN AAPKO JALD REPLY KAREGA.",
            parse_mode="Markdown",
            reply_markup=get_support_reply_keyboard(),
        )


# ============================================================
# SETUP CHANNEL CALLBACKS (SEND SAVED APK & JOIN CHANNEL BUTTON)
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("setup_"))
def handle_setup_callbacks(call):
    bot.answer_callback_query(call.id)
    key = call.data.replace("setup_", "")

    loader_doc = loaders_collection.find_one({"loader_key": key})
    video_link = loader_doc.get("video_link", "https://t.me/VoltageLoader") if loader_doc else "https://t.me/VoltageLoader"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 JOIN OFFICIAL CHANNEL", url=video_link)
    )

    if loader_doc and "file_id" in loader_doc:
        file_id = loader_doc["file_id"]
        try:
            bot.send_document(
                call.message.chat.id,
                document=file_id,
                caption=(
                    f"📁 *HERE IS YOUR APK FOR {key.upper().replace('_', ' ')}* ✅\n\n"
                    f"NICHE DIYE GAYE BUTTON SE OFFICIAL CHANNEL JOIN KAREIN:"
                ),
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                f"❌ APK SEND KARNE MEIN ERROR AAYA. KRIPYA ADMIN SE DOBARA UPLOAD KARWAYEIN.\n\n📢 OFFICIAL CHANNEL LINK:",
                parse_mode="Markdown",
                reply_markup=markup
            )
    else:
        bot.send_message(
            call.message.chat.id,
            f"❌ *APK NOT AVAILABLE YET!*\nADMIN NE ABHI IS LOADER KE LIYE APK UPLOAD NAHI KIYA HAI.\n\n📢 OFFICIAL CHANNEL LINK:",
            parse_mode="Markdown",
            reply_markup=markup
        )


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
    text = (message.text or "").strip()

    if text == "🔚 BACK":
        if user_id in user_states:
            del user_states[user_id]
        bot.send_message(
            message.chat.id,
            "🏠 *MAIN MENU:* ✅",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )
        return

    if text == "📞 CONTACT OWNER":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "💬 OPEN OWNER DM",
                url=f"https://t.me/{OWNER_USERNAME}"
            )
        )
        bot.send_message(
            message.chat.id,
            "💬 *CLICK THE BUTTON BELOW TO OPEN OWNER DM DIRECTLY:* ✅",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return

    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "NO USERNAME"
        first_name = user.first_name if user.first_name else "USER"

        info_text = (
            f"📩 *NEW SUPPORT MESSAGE FROM USER* ✅\n"
            f"👤 NAME: {first_name}\n"
            f"🆔 USER ID: `{user.id}`\n"
            f"🔗 USERNAME: {username}"
        )

        sent_info = bot.send_message(ADMIN_ID, info_text, parse_mode="Markdown")
        sent_forward = bot.forward_message(ADMIN_ID, message.chat.id, message.id)

        admin_reply_map[sent_info.message_id] = user.id
        admin_reply_map[sent_forward.message_id] = user.id
    except Exception as e:
        print(f"ERROR FORWARDING SUPPORT MESSAGE TO ADMIN: {e}")


# ============================================================
# HANDLE USER DELETE KEY FROM "MY KEYS"
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("delmykey_"))
def handle_delete_my_key(call):
    user_id = call.from_user.id
    try:
        key_id = int(call.data.split("_")[1])
    except Exception:
        bot.answer_callback_query(call.id, "❌ INVALID KEY ID!", show_alert=True)
        return

    result = keys_collection.delete_one({"id": key_id, "assigned_to": user_id})
    if result.deleted_count > 0:
        bot.answer_callback_query(call.id, "✅ KEY SUCCESSFULLY DELETE KAR DI GAYI HAI!", show_alert=True)
        try:
            bot.edit_message_text("❌ *KEY SUCCESSFULLY DELETE KAR DI GAYI HAI!* ✅", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "❌ YEH KEY AAPKO ASSIGNED NAHI HAI YA PEHLE HI DELETE HO CHUKI HAI!", show_alert=True)


# ============================================================
# HANDLE PLAN
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def handle_plan(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    amount = int(parts[-1])
    duration = "_".join(parts[1:-1]).replace("_", " ")
    user_id = call.from_user.id
    current_time = time.time()

    order_id = get_next_id("orders")
    orders_collection.insert_one({"id": order_id, "user_id": user_id, "duration": duration, "amount": amount, "created_at": current_time, "status": "pending"})

    unique_tr = f"R2F{order_id}{int(current_time)}"
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

    caption_text = (
        "💳 *SCAN & PAY* ✅\n\n"
        f"• *PLAN:* {duration}\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
        "1️⃣ PEHLE PAYMENT KAREIN.\n"
        "2️⃣ APNE **PAYMENT SCREENSHOT** KO YAHIN CHAT MEIN SEND KAREIN."
    )

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
    state = user_states[user_id]

    if message.text:
        text = message.text.strip()
        if "ORDER CANCEL" in text.upper():
            handle_cancel_button(message)
            return

        if any(menu_item in text.upper() for menu_item in ["🛒 PURCHASE KEY", "🔐 MY KEYS", "🔑 GENERATE KEY", "♻️ APK & SETUP", "💬 CONTACT SUPPORT", "🔚 BACK", "👑 SUPER ADMIN"]) or text.startswith("/"):
            if user_id in user_states and "qr_msg_id" in user_states[user_id]:
                try:
                    bot.delete_message(message.chat.id, user_states[user_id]["qr_msg_id"])
                except Exception:
                    pass
            del user_states[user_id]

            if "BACK" in text.upper():
                handle_back_button(message)
            elif "SUPER ADMIN" in text.upper():
                super_admin_panel(message)
            elif "GENERATE KEY" in text.upper():
                handle_gen_key_menu(message)
            else:
                handle_reply_menu(message)
            return

        bot.reply_to(message, "❌ KRIPYA TEXT KI JAGAH APNA **PAYMENT SCREENSHOT** BHEIN!", reply_markup=get_payment_reply_keyboard())
        return

    if message.photo:
        order_id = state["order_id"]
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
            "⏳ *SCREENSHOT SUBMITTED SUCCESSFULLY!* ✅\nAAPKA SCREENSHOT ADMIN KE PAAS VERIFICATION KE LIYE BHEJ DIYA GAYA HAI.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
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
            f"🔔 *NEW PAYMENT SCREENSHOT VERIFICATION!* ✅\n\n"
            f"👤 *USER:* {first_name} ({username_str})\n"
            f"🆔 *USER ID:* `{user_id}`\n"
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
        key_row = keys_collection.find_one({"duration": duration, "status": "unused"}, {"id": 1, "license_key": 1})
        if not key_row:
            bot.answer_callback_query(call.id, "❌ OUT OF STOCK!", show_alert=True)
            return

        key_id = key_row["id"]
        license_key = key_row["license_key"]

        assigned_key = keys_collection.find_one_and_update(
            {"id": key_id, "status": "unused"},
            {"$set": {"status": "used", "assigned_to": user_id}},
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
                f"STATUS: *✅ APPROVED (YES)* ✅\n"
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
                f"🎉 *PAYMENT VERIFIED & APPROVED BY ADMIN!* ✅\n\n• *PLAN:* {duration}\n• *YOUR LICENSE KEY:*\n`{license_key}`",
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard(user_id),
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
                reply_markup=get_main_reply_keyboard(user_id),
            )
        except Exception:
            pass


# ============================================================
# CANCEL ORDER
# ============================================================

@bot.message_handler(func=lambda message: "ORDER CANCEL" in (message.text or "").upper())
def handle_cancel_button(message):
    user_id = message.from_user.id
    if user_id not in user_states:
        bot.send_message(message.chat.id, "❌ ACTION CANCELLED.", reply_markup=get_main_reply_keyboard(user_id))
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

    bot.send_message(message.chat.id, "❌ PAYMENT CANCELLED SUCCESSFULLY.", reply_markup=get_main_reply_keyboard(user_id))


# ============================================================
# RESET KEY
# ============================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("reset_"))
def handle_reset_key(call):
    key_id = call.data.split("_")[1]
    user_id = call.from_user.id

    bot.answer_callback_query(call.id, "🔄 RESET REQUEST SENT TO OWNER/ADMIN SUCCESSFULLY! ✅", show_alert=True)
    bot.send_message(ADMIN_ID, f"⚠ *KEY RESET REQUEST*\nUSER ID: `{user_id}` REQUESTED RESET FOR KEY ID: `{key_id}`", parse_mode="Markdown")


# ============================================================
# CATCH-ALL: FORWARD USER MESSAGES TO ADMIN
# ============================================================

@bot.message_handler(
    func=lambda message: message.from_user.id != ADMIN_ID and message.from_user.id not in user_states,
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def forward_user_messages_to_admin(message):
    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "NO USERNAME"
        first_name = user.first_name if user.first_name else "USER"

        info_text = f"📩 *NEW MESSAGE FROM USER* ✅\n👤 NAME: {first_name}\n🆔 USER ID: `{user.id}`\n🔗 USERNAME: {username}"

        sent_info = bot.send_message(ADMIN_ID, info_text, parse_mode="Markdown")
        sent_forward = bot.forward_message(ADMIN_ID, message.chat.id, message.id)

        admin_reply_map[sent_info.message_id] = user.id
        admin_reply_map[sent_forward.message_id] = user.id
    except Exception as e:
        print(f"ERROR FORWARDING MESSAGE TO ADMIN: {e}")


# ============================================================
# ADMIN REPLY TO USER
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

    if target_user_id:
        try:
            bot.copy_message(chat_id=target_user_id, from_chat_id=message.chat.id, message_id=message.id)
            bot.reply_to(message, "✅ *REPLY SUCCESSFULLY SENT TO USER!* ✅", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ FAILED TO SEND REPLY: `{e}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ TARGET USER ID NAHI MILA. KRIPYA USER KE **INFO MESSAGE** PAR REPLY KAREIN.", parse_mode="Markdown")


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
        bot.delete_webhook(drop_
