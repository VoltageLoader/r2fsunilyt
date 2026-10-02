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
    raise ValueError("BOT_TOKEN environment variable is not set")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")


ADMIN_ID = 6795305850
UPI_ID = "8905094188@ybl"
UPI_NAME = "NEXA CYBER"
OWNER_USERNAME = "R2FSUNILYT"
SETUP_CHANNEL_URL = "https://t.me/VoltageLoader"


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

    # Test connection
    mongo_client.admin.command("ping")

    # Database name
    db = mongo_client["r2f_bot"]

    # Collections
    keys_collection = db["keys_table"]
    orders_collection = db["orders"]
    reseller_orders_collection = db["reseller_orders"]
    resellers_collection = db["resellers"]
    counters_collection = db["counters"]

    # Unique license key
    keys_collection.create_index(
        [("license_key", ASCENDING)],
        unique=True,
        name="unique_license_key",
    )

    # Useful indexes
    keys_collection.create_index(
        [("duration", ASCENDING), ("status", ASCENDING)]
    )

    keys_collection.create_index(
        [("assigned_to", ASCENDING), ("status", ASCENDING)]
    )

    orders_collection.create_index(
        [("user_id", ASCENDING)]
    )

    orders_collection.create_index(
        [("utr", ASCENDING)]
    )

    reseller_orders_collection.create_index(
        [("user_id", ASCENDING)]
    )

    reseller_orders_collection.create_index(
        [("utr", ASCENDING)]
    )

    resellers_collection.create_index(
        [("user_id", ASCENDING)],
        unique=True,
    )

    print("MongoDB connected successfully!")

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
    order_id,
    action_type="plan"
):
    time.sleep(300)

    try:
        if action_type == "plan":
            row = orders_collection.find_one(
                {"id": order_id},
                {"status": 1}
            )
        else:
            row = reseller_orders_collection.find_one(
                {"id": order_id},
                {"status": 1}
            )

        if row and row.get("status") in ["pending", "pending_admin"]:
            try:
                bot.send_message(
                    chat_id,
                    "⏳ PAYMENT TIME EXPIRED\n"
                    "❌ APPROVAL REQUEST CLOSED\n"
                    f"📩 TRY AGAIN — CONTACT: @{OWNER_USERNAME}",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard(user_id),
                )
            except Exception:
                pass

    except Exception as e:
        print(f"Timeout worker error: {e}")


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

    markup.add(
        types.KeyboardButton("🤝 BUY RESELLERSHIP")
    )

    markup.add(
        types.KeyboardButton("♻️ SETUP CHANNEL"),
        types.KeyboardButton("💬 CONTACT SUPPORT")
    )

    if user_id == ADMIN_ID:
        markup.add(
            types.KeyboardButton("👑 SUPER ADMIN")
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
        row_width=2
    )

    markup.add(
        types.KeyboardButton("✅ PAYMENT DONE"),
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
        "👋 *WELCOME TO R2F OFFICIAL KEY STORE!*\n\n"
        "👉 *CLICK THE MENU BUTTONS BELOW:* 👇\n\n"
        "🛒 *PURCHASE KEY*\n"
        "🔐 *MY KEYS*\n"
        "🤝 *BUY RESELLERSHIP*\n"
        "♻️ *SETUP CHANNEL*\n"
        "💬 *CONTACT SUPPORT*"
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
        "🏠 *MAIN MENU:*",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(user_id),
    )


# ============================================================
# SUPER ADMIN PANEL
# ============================================================

@bot.message_handler(func=lambda message: message.text == "👑 SUPER ADMIN")
def super_admin_panel(message):

    if message.from_user.id != ADMIN_ID:
        bot.reply_to(
            message,
            "❌ YOU ARE NOT AUTHORIZED!"
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)

    markup.add(
        types.InlineKeyboardButton(
            "➕ ADD SINGLE KEY",
            callback_data="sa_add_single"
        ),
        types.InlineKeyboardButton(
            "📦 ADD BULK KEY",
            callback_data="sa_add_bulk"
        ),
        types.InlineKeyboardButton(
            "❌ DELETE SINGLE KEY",
            callback_data="sa_del_single"
        ),
        types.InlineKeyboardButton(
            "🗑️ DELETE BULK KEYS",
            callback_data="sa_del_bulk"
        ),
        types.InlineKeyboardButton(
            "📋 SHOW ALL KEYS",
            callback_data="sa_show_keys"
        ),
    )

    bot.send_message(
        message.chat.id,
        "👑 *SUPER ADMIN PANEL*\n\n"
        "Niche diye gaye options mein se select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ============================================================
# SUPER ADMIN CALLBACKS
# ============================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("sa_")
)
def super_admin_callbacks(call):

    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(
            call.id,
            "❌ Unauthorized!",
            show_alert=True
        )
        return

    data = call.data

    # --------------------------------------------------------
    # ADD SINGLE
    # --------------------------------------------------------

    if data == "sa_add_single":

        bot.answer_callback_query(call.id)

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
                    f"⏱ {d}",
                    callback_data=f"sa_sdur_{cb_val}"
                )
            )

        bot.edit_message_text(
            "➕ *ADD SINGLE KEY*\n\n"
            "Duration select karein:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data.startswith("sa_sdur_"):

        duration = data.replace(
            "sa_sdur_",
            ""
        ).replace(
            "_",
            " "
        )

        bot.answer_callback_query(call.id)

        user_states[ADMIN_ID] = {
            "type": "waiting_single_key",
            "duration": duration
        }

        bot.send_message(
            call.message.chat.id,
            f"➕ *ADD SINGLE KEY*\n\n"
            f"Duration: *{duration}*\n\n"
            "💬 Ab apni **License Key** yahan chat mein send karein:",
            parse_mode="Markdown",
        )

    # --------------------------------------------------------
    # ADD BULK
    # --------------------------------------------------------

    elif data == "sa_add_bulk":

        bot.answer_callback_query(call.id)

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
                    f"⏱ {d}",
                    callback_data=f"sa_bdur_{cb_val}"
                )
            )

        bot.edit_message_text(
            "📦 *ADD BULK KEYS*\n\n"
            "Duration select karein:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data.startswith("sa_bdur_"):

        duration = data.replace(
            "sa_bdur_",
            ""
        ).replace(
            "_",
            " "
        )

        bot.answer_callback_query(call.id)

        user_states[ADMIN_ID] = {
            "type": "waiting_bulk_keys",
            "duration": duration
        }

        bot.send_message(
            call.message.chat.id,
            f"📦 *ADD BULK KEYS*\n\n"
            f"Duration: *{duration}*\n\n"
            "💬 Ab multiple keys **ek line mein ek key** karke yahan paste/send karein:",
            parse_mode="Markdown",
        )

    # --------------------------------------------------------
    # DELETE SINGLE
    # --------------------------------------------------------

    elif data == "sa_del_single":

        bot.answer_callback_query(call.id)

        user_states[ADMIN_ID] = {
            "type": "waiting_del_id"
        }

        bot.send_message(
            call.message.chat.id,
            "❌ *DELETE SINGLE KEY*\n\n"
            "💬 Jis key ko delete karna hai uska **Key ID** yahan send karein:",
            parse_mode="Markdown",
        )

    # --------------------------------------------------------
    # DELETE BULK
    # --------------------------------------------------------

    elif data == "sa_del_bulk":

        bot.answer_callback_query(call.id)

        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(
            types.InlineKeyboardButton(
                "📋 PASTE KEYS TO DELETE IN BULK",
                callback_data="sa_del_paste_bulk"
            ),
            types.InlineKeyboardButton(
                "🗑️ DELETE ALL UNUSED KEYS",
                callback_data="sa_del_all_unused"
            ),
        )

        bot.edit_message_text(
            "🗑️ *DELETE BULK OPTIONS*\n\n"
            "Option select karein:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    elif data == "sa_del_paste_bulk":

        bot.answer_callback_query(call.id)

        user_states[ADMIN_ID] = {
            "type": "waiting_bulk_del"
        }

        bot.send_message(
            call.message.chat.id,
            "🗑 *DELETE BULK KEYS BY LIST*\n\n"
            "💬 Jin keys ko delete karna hai unhe "
            "**ek line mein ek key** karke yahan send karein:",
            parse_mode="Markdown",
        )

    elif data == "sa_del_all_unused":

        bot.answer_callback_query(call.id)

        result = keys_collection.delete_many(
            {"status": "unused"}
        )

        deleted_count = result.deleted_count

        bot.send_message(
            call.message.chat.id,
            "✅ Saari unused keys successfully delete kar di gayi hain!\n\n"
            f"Total deleted: `{deleted_count}`",
            parse_mode="Markdown",
        )

    # --------------------------------------------------------
    # SHOW ALL KEYS
    # --------------------------------------------------------

    elif data == "sa_show_keys":

        bot.answer_callback_query(call.id)

        keys = list(
            keys_collection.find(
                {},
                {
                    "id": 1,
                    "duration": 1,
                    "license_key": 1,
                    "status": 1,
                    "assigned_to": 1
                }
            ).sort(
                "id",
                DESCENDING
            ).limit(50)
        )

        if not keys:

            bot.send_message(
                call.message.chat.id,
                "❌ Database mein koi keys available nahi hain."
            )

            return

        text = "📋 *ALL STORED KEYS (Last 50):*\n\n"

        markup = types.InlineKeyboardMarkup(row_width=2)

        for key in keys:

            kid = key["id"]
            duration = key.get("duration", "")
            license_key = key.get("license_key", "")
            status = key.get("status", "unused")
            assigned_to = key.get("assigned_to")

            if status == "unused":
                status_icon = "🟢 Unused"
            else:
                status_icon = f"🔴 Used (User: {assigned_to})"

            text += (
                f"🆔 ID: `{kid}` | *{duration}*\n"
                f"🔑 `{license_key}`\n"
                f"Status: {status_icon}\n\n"
            )

            markup.add(
                types.InlineKeyboardButton(
                    f"🗑️ Delete ID {kid}",
                    callback_data=f"sa_del_id_{kid}"
                )
            )

        bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    # --------------------------------------------------------
    # DELETE KEY BY ID
    # --------------------------------------------------------

    elif data.startswith("sa_del_id_"):

        kid = int(
            data.split("_")[3]
        )

        result = keys_collection.delete_one(
            {"id": kid}
        )

        bot.answer_callback_query(
            call.id,
            f"✅ Key ID {kid} deleted successfully!",
            show_alert=True
        )

        try:

            if result.deleted_count:

                bot.edit_message_text(
                    f"✅ *Key ID `{kid}` Successfully Deleted!*",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

            else:

                bot.edit_message_text(
                    f"❌ *Key ID `{kid}` NOT FOUND!*",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

        except Exception:
            pass


# ============================================================
# ADMIN STATE INPUT
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.from_user.id in user_states
        and user_states[message.from_user.id]["type"]
        in [
            "waiting_single_key",
            "waiting_bulk_keys",
            "waiting_del_id",
            "waiting_bulk_del",
        ]
)
def handle_admin_state_input(message):

    user_id = message.from_user.id

    state = user_states[user_id]

    action_type = state["type"]

    text = (message.text or "").strip()

    if text.startswith("/") or text in [
        "🛒 PURCHASE KEY",
        "🔐 MY KEYS",
        "🤝 BUY RESELLERSHIP",
        "♻️ SETUP CHANNEL",
        "💬 CONTACT SUPPORT",
        "🔚 BACK",
        "👑 SUPER ADMIN",
    ]:

        del user_states[user_id]

        if text == "👑 SUPER ADMIN":
            super_admin_panel(message)

        elif text == "🔚 BACK":
            handle_back_button(message)

        else:
            handle_reply_menu(message)

        return

    # --------------------------------------------------------
    # SINGLE KEY
    # --------------------------------------------------------

    if action_type == "waiting_single_key":

        duration = state["duration"]

        license_key = text

        try:

            new_id = get_next_id("keys")

            keys_collection.insert_one(
                {
                    "id": new_id,
                    "duration": duration,
                    "license_key": license_key,
                    "status": "unused",
                    "assigned_to": None,
                }
            )

            del user_states[user_id]

            bot.reply_to(
                message,
                f"✅ *SINGLE KEY ADDED SUCCESSFULLY!*\n\n"
                f"• *DURATION:* {duration}\n"
                f"• *KEY:* `{license_key}`",
                parse_mode="Markdown",
            )

        except DuplicateKeyError:

            bot.reply_to(
                message,
                "❌ *DUPLICATE KEY ERROR!*\n"
                "Yeh license key pehle se database mein mojood hai.",
                parse_mode="Markdown",
            )

        except Exception as e:

            print(f"Single key error: {e}")

            bot.reply_to(
                message,
                "❌ Key add karte waqt database error aa gaya.",
            )

    # --------------------------------------------------------
    # BULK KEYS
    # --------------------------------------------------------

    elif action_type == "waiting_bulk_keys":

        duration = state["duration"]

        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

        if not lines:

            bot.reply_to(
                message,
                "❌ Koi keys nahi mili!"
            )

            return

        added_count = 0
        duplicate_count = 0

        for key in lines:

            try:

                new_id = get_next_id("keys")

                keys_collection.insert_one(
                    {
                        "id": new_id,
                        "duration": duration,
                        "license_key": key,
                        "status": "unused",
                        "assigned_to": None,
                    }
                )

                added_count += 1

            except DuplicateKeyError:

                duplicate_count += 1

            except Exception as e:

                print(f"Bulk key error: {e}")

        del user_states[user_id]

        bot.reply_to(
            message,
            f"📦 *BULK KEYS ADDED REPORT*\n\n"
            f"• *DURATION:* {duration}\n"
            f"• *Successfully Added:* `{added_count}`\n"
            f"• *Exact Duplicates Skipped:* `{duplicate_count}`",
            parse_mode="Markdown",
        )

    # --------------------------------------------------------
    # DELETE SINGLE ID
    # --------------------------------------------------------

    elif action_type == "waiting_del_id":

        try:

            key_id = int(text)

            result = keys_collection.delete_one(
                {"id": key_id}
            )

            del user_states[user_id]

            if result.deleted_count:

                bot.reply_to(
                    message,
                    f"✅ Key ID `{key_id}` successfully delete kar di gayi hai!",
                    parse_mode="Markdown",
                )

            else:

                bot.reply_to(
                    message,
                    f"❌ Key ID `{key_id}` nahi mili.",
                    parse_mode="Markdown",
                )

        except Exception:

            bot.reply_to(
                message,
                "❌ Sahi Key ID enter karein (Sirf number hona chahiye).",
                parse_mode="Markdown",
            )

    # --------------------------------------------------------
    # BULK DELETE
    # --------------------------------------------------------

    elif action_type == "waiting_bulk_del":

        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

        if not lines:

            bot.reply_to(
                message,
                "❌ Koi keys nahi mili!"
            )

            return

        deleted_count = 0

        for key in lines:

            result = keys_collection.delete_one(
                {"license_key": key}
            )

            deleted_count += result.deleted_count

        del user_states[user_id]

        bot.reply_to(
            message,
            f"🗑️ *BULK DELETE REPORT*\n\n"
            f"• *Total Keys Deleted:* `{deleted_count}`",
            parse_mode="Markdown",
        )


# ============================================================
# REPLY MENU
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.text in [
            "🛒 PURCHASE KEY",
            "🔐 MY KEYS",
            "🤝 BUY RESELLERSHIP",
            "♻️ SETUP CHANNEL",
            "💬 CONTACT SUPPORT",
        ]
)
def handle_reply_menu(message):

    user_id = message.from_user.id

    if user_id in user_states:
        del user_states[user_id]

    # --------------------------------------------------------
    # PURCHASE KEY
    # --------------------------------------------------------

    if message.text == "🛒 PURCHASE KEY":

        markup = types.InlineKeyboardMarkup(
            row_width=2
        )

        plans = [
            ("⏱ 5 HOUR - ₹30", "5 Hour", 30),
            ("⏱ 1 DAY - ₹99", "1 Day", 99),
            ("⏱ 2 DAY - ₹149", "2 Day", 149),
            ("⏱ 3 DAY - ₹199", "3 Day", 199),
            ("⏱ 7 DAY - ₹399", "7 Day", 399),
            ("⏱ 30 DAY - ₹799", "30 Day", 799),
        ]

        for title, duration, amount in plans:

            stock_count = keys_collection.count_documents(
                {
                    "duration": duration,
                    "status": "unused"
                }
            )

            button_title = (
                f"{title} | STOCK: {stock_count}"
            )

            cb_duration = duration.replace(
                " ",
                "_"
            )

            markup.add(
                types.InlineKeyboardButton(
                    button_title,
                    callback_data=f"plan_{cb_duration}_{amount}"
                )
            )

        bot.send_message(
            message.chat.id,
            "📋 *SELECT PLAN*\n\n"
            "APNA PLAN SELECT KAREIN:",
            parse_mode="Markdown",
            reply_markup=markup,
        )

        bot.send_message(
            message.chat.id,
            "👇 PICHE JAANE KE LIYE NICHE **🔚 BACK** DABAYEIN:",
            reply_markup=get_back_reply_keyboard(),
        )

    # --------------------------------------------------------
    # MY KEYS
    # --------------------------------------------------------

    elif message.text == "🔐 MY KEYS":

        keys = list(
            keys_collection.find(
                {
                    "status": "used",
                    "assigned_to": user_id
                },
                {
                    "id": 1,
                    "duration": 1,
                    "license_key": 1
                }
            ).sort(
                "id",
                DESCENDING
            )
        )

        if not keys:

            bot.send_message(
                message.chat.id,
                "❌ AAPKE PAAS KOI ACTIVE KEY NAHI HAI!",
                parse_mode="Markdown",
            )

            return

        markup = types.InlineKeyboardMarkup(
            row_width=1
        )

        text = "🔐 *YOUR PURCHASED KEYS:*\n\n"

        for key in keys:

            key_id = key["id"]
            duration = key["duration"]
            license_key = key["license_key"]

            text += (
                f"• *Plan:* ({duration})\n"
                f"🔑 `{license_key}`\n\n"
            )

            markup.add(
                types.InlineKeyboardButton(
                    f"🔄 RESET KEY ({duration})",
                    callback_data=f"reset_{key_id}",
                )
            )

        bot.send_message(
            message.chat.id,
            text,
            parse_mode="Markdown",
            reply_markup=markup,
        )

    # --------------------------------------------------------
    # RESELLERSHIP
    # --------------------------------------------------------

    elif message.text == "🤝 BUY RESELLERSHIP":

        amount = 1599

        current_time = time.time()

        order_id = get_next_id(
            "reseller_orders"
        )

        reseller_orders_collection.insert_one(
            {
                "id": order_id,
                "user_id": user_id,
                "utr": "",
                "amount": amount,
                "created_at": current_time,
                "status": "pending",
            }
        )

        unique_tr = (
            f"R2FRES{order_id}{int(current_time)}"
        )

        upi_url = (
            f"upi://pay?"
            f"pa={UPI_ID}"
            f"&pn={UPI_NAME}"
            f"&am={amount}.00"
            f"&cu=INR"
            f"&tr={unique_tr}"
        )

        qr_api_url = (
            "https://api.qrserver.com/v1/create-qr-code/"
            f"?size=300x300&data={urllib.parse.quote(upi_url)}"
        )

        caption_text = (
            "💳 *SCAN & PAY*\n\n"
            "• *LOADER:* RESELLER SHIP (1 MONTH)\n"
            f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
            f"• *UPI ID:* `{UPI_ID}`\n\n"
            "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
            "1️⃣ PEHLE PAYMENT KAREIN.\n"
            "2️⃣ **12-DIGIT UTR** AUR **PAYMENT SCREENSHOT** "
            "DONO YAHIN CHAT MEIN SEND KAREIN.\n"
            "3️⃣ SEND KARNE KE BAAD NICHE MENU MEIN "
            "**✅ PAYMENT DONE** PAR CLICK KAREIN."
        )

        sent_msg = bot.send_photo(
            chat_id=message.chat.id,
            photo=qr_api_url,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=get_payment_reply_keyboard(),
        )

        user_states[user_id] = {
            "type": "reseller",
            "order_id": order_id,
            "timestamp": current_time,
            "amount": amount,
            "qr_msg_id": sent_msg.message_id,
        }

        threading.Thread(
            target=send_timeout_failed_message,
            args=(
                message.chat.id,
                user_id,
                order_id,
                "reseller"
            ),
            daemon=True,
        ).start()

    # --------------------------------------------------------
    # SETUP CHANNEL
    # --------------------------------------------------------

    elif message.text == "♻️ SETUP CHANNEL":

        markup = types.InlineKeyboardMarkup()

        markup.add(
            types.InlineKeyboardButton(
                "🔗 OPEN SETUP CHANNEL",
                url=SETUP_CHANNEL_URL
            )
        )

        bot.send_message(
            message.chat.id,
            "♻️️ *CLICK THE BUTTON BELOW TO OPEN SETUP CHANNEL:*",
            parse_mode="Markdown",
            reply_markup=markup,
        )

    # --------------------------------------------------------
    # CONTACT SUPPORT
    # --------------------------------------------------------

    elif message.text == "💬 CONTACT SUPPORT":

        markup = types.InlineKeyboardMarkup()

        markup.add(
            types.InlineKeyboardButton(
                "💬 OPEN SUPPORT CHAT",
                url=f"https://t.me/{OWNER_USERNAME}"
            )
        )

        bot.send_message(
            message.chat.id,
            "💬 *CLICK THE BUTTON BELOW TO CONTACT SUPPORT:*",
            parse_mode="Markdown",
            reply_markup=markup,
        )


# ============================================================
# HANDLE PLAN
# ============================================================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("plan_")
)
def handle_plan(call):

    bot.answer_callback_query(call.id)

    parts = call.data.split("_")

    amount = int(parts[-1])

    duration = "_".join(
        parts[1:-1]
    ).replace(
        "_",
        " "
    )

    user_id = call.from_user.id

    current_time = time.time()

    order_id = get_next_id(
        "orders"
    )

    orders_collection.insert_one(
        {
            "id": order_id,
            "user_id": user_id,
            "utr": "",
            "duration": duration,
            "amount": amount,
            "created_at": current_time,
            "status": "pending",
        }
    )

    unique_tr = (
        f"R2F{order_id}{int(current_time)}"
    )

    upi_url = (
        f"upi://pay?"
        f"pa={UPI_ID}"
        f"&pn={UPI_NAME}"
        f"&am={amount}.00"
        f"&cu=INR"
        f"&tr={unique_tr}"
    )

    qr_api_url = (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size=300x300&data={urllib.parse.quote(upi_url)}"
    )

    caption_text = (
        "💳 *SCAN & PAY*\n\n"
        f"• *PLAN:* {duration}\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
        "1️⃣ PEHLE PAYMENT KAREIN.\n"
        "2️⃣ **12-DIGIT UTR** AUR **PAYMENT SCREENSHOT** "
        "DONO YAHIN CHAT MEIN SEND KAREIN.\n"
        "3️⃣ SEND KARNE KE BAAD NICHE MENU MEIN "
        "**✅ PAYMENT DONE** PAR CLICK KAREIN."
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
        args=(
            call.message.chat.id,
            user_id,
            order_id,
            "plan"
        ),
        daemon=True,
    ).start()


# ============================================================
# HANDLE UTR / SCREENSHOT
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id in user_states
        and user_states[message.from_user.id]["type"]
        in ["plan", "reseller"],
    content_types=["text", "photo"],
)
def handle_utr_text(message):

    user_id = message.from_user.id

    state = user_states[user_id]

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    if message.photo:

        caption = message.caption or ""

        match = re.search(
            r"\b\d{12}\b",
            caption
        )

        if match:

            utr = match.group(0)

        else:

            bot.reply_to(
                message,
                "📸 *Screenshot Mil Gaya!*\n"
                "Ab apna **12-digit UTR number** bhi "
                "yahin chat mein text karke bhej dein:",
                parse_mode="Markdown",
                reply_markup=get_payment_reply_keyboard(),
            )

            return

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    else:

        text = message.text or ""

        if "PAYMENT DONE" in text.upper():

            handle_payment_done_button(message)
            return

        elif "ORDER CANCEL" in text.upper():

            handle_cancel_button(message)
            return

        if any(
            menu_item in text.upper()
            for menu_item in [
                "🛒 PURCHASE KEY",
                "🔐 MY KEYS",
                "🤝 BUY RESELLERSHIP",
                "♻️ SETUP CHANNEL",
                "💬 CONTACT SUPPORT",
                "🔚 BACK",
                "👑 SUPER ADMIN",
            ]
        ) or text.startswith("/"):

            if (
                user_id in user_states
                and "qr_msg_id" in user_states[user_id]
            ):

                try:
                    bot.delete_message(
                        message.chat.id,
                        user_states[user_id]["qr_msg_id"]
                    )
                except Exception:
                    pass

            del user_states[user_id]

            if "BACK" in text.upper():

                handle_back_button(message)

            elif "SUPER ADMIN" in text.upper():

                super_admin_panel(message)

            else:

                handle_reply_menu(message)

            return

        raw_text = text.strip()

        match = re.search(
            r"\b\d{12}\b",
            raw_text
        )

        if match:

            utr = match.group(0)

        else:

            cleaned = "".join(
                filter(
                    str.isdigit,
                    raw_text
                )
            )

            if len(cleaned) == 12:

                utr = cleaned

            else:

                bot.reply_to(
                    message,
                    "❌ *INVALID UTR FORMAT!*\n"
                    "KRIPYA APNA **12-DIGIT NUMERIC UTR** DOBARA BHEJEIN:",
                    parse_mode="Markdown",
                    reply_markup=get_payment_reply_keyboard(),
                )

                return

    # ========================================================
    # CHECK DUPLICATE UTR
    # ========================================================

    used_in_orders = orders_collection.find_one(
        {
            "utr": utr,
            "status": "approved"
        },
        {"id": 1}
    )

    used_in_resellers = reseller_orders_collection.find_one(
        {
            "utr": utr,
            "status": "approved"
        },
        {"id": 1}
    )

    if used_in_orders or used_in_resellers:

        bot.reply_to(
            message,
            "❌ *FRAUD ALERT!* "
            "YEH UTR NUMBER PEHLE HI USE KIYA JA CHUKA HAI.",
            parse_mode="Markdown",
            reply_markup=get_payment_reply_keyboard(),
        )

        return

    # ========================================================
    # SAVE UTR
    # ========================================================

    order_id = state["order_id"]

    action_type = state["type"]

    if action_type == "plan":

        orders_collection.update_one(
            {"id": order_id},
            {"$set": {"utr": utr}}
        )

    else:

        reseller_orders_collection.update_one(
            {"id": order_id},
            {"$set": {"utr": utr}}
        )

    bot.reply_to(
        message,
        "✅ *UTR VERIFIED & SAVED SUCCESSFULLY!*\n"
        "Ab niche menu mein diye gaye "
        "**✅ PAYMENT DONE** button par click karein.",
        parse_mode="Markdown",
        reply_markup=get_payment_reply_keyboard(),
    )


# ============================================================
# PAYMENT DONE
# ============================================================

@bot.message_handler(
    func=lambda message:
        "PAYMENT DONE" in (message.text or "").upper()
)
def handle_payment_done_button(message):

    user_id = message.from_user.id

    if user_id not in user_states:

        bot.send_message(
            message.chat.id,
            "❌ KOI ACTIVE PAYMENT SESSION NAHI MILA. "
            "KRIPYA /start DABAYEIN.",
            reply_markup=get_main_reply_keyboard(user_id),
        )

        return

    state = user_states[user_id]

    if "qr_msg_id" in state:

        try:
            bot.delete_message(
                message.chat.id,
                state["qr_msg_id"]
            )
        except Exception:
            pass

    order_id = state["order_id"]

    action_type = state["type"]

    # --------------------------------------------------------
    # GET ORDER
    # --------------------------------------------------------

    if action_type == "plan":

        row = orders_collection.find_one(
            {"id": order_id}
        )

    else:

        row = reseller_orders_collection.find_one(
            {"id": order_id}
        )

    if not row:

        bot.send_message(
            message.chat.id,
            "❌ ORDER NOT FOUND!",
            reply_markup=get_main_reply_keyboard(user_id),
        )

        return

    utr = row.get("utr", "")

    if not utr or len(utr) != 12:

        bot.send_message(
            message.chat.id,
            "❌ PEHLE APNA VALID 12-DIGIT UTR CHAT MEIN SEND KAREIN, "
            "FIR PAYMENT DONE DABAYEIN!",
            reply_markup=get_payment_reply_keyboard(),
        )

        return

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------

    if action_type == "plan":

        duration = row["duration"]

        amount = row["amount"]

        orders_collection.update_one(
            {"id": order_id},
            {"$set": {"status": "pending_admin"}}
        )

        del user_states[user_id]

        bot.send_message(
            message.chat.id,
            "⏳ *PAYMENT SUBMITTED SUCCESSFULLY!*\n"
            "AAPKA UTR ADMIN KE PAAS APPROVAL KE LIYE BHEJ DIYA GAYA HAI.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )

        markup = types.InlineKeyboardMarkup(
            row_width=2
        )

        markup.add(
            types.InlineKeyboardButton(
                "✅ APPROVE",
                callback_data=f"adm_app_plan_{order_id}"
            ),
            types.InlineKeyboardButton(
                "❌ REJECT",
                callback_data=f"adm_rej_plan_{order_id}"
            ),
        )

        admin_text = (
            f"🔔 *NEW PAYMENT APPROVAL REQUEST!*\n\n"
            f"👤 *USER ID:* `{user_id}`\n"
            f"⏱ *PLAN:* {duration}\n"
            f"💵 *AMOUNT:* ₹{amount}\n"
            f"💳 *UTR NUMBER:* `{utr}`"
        )

        try:

            bot.send_message(
                ADMIN_ID,
                admin_text,
                parse_mode="Markdown",
                reply_markup=markup
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # RESELLER
    # --------------------------------------------------------

    else:

        amount = row["amount"]

        reseller_orders_collection.update_one(
            {"id": order_id},
            {"$set": {"status": "pending_admin"}}
        )

        del user_states[user_id]

        bot.send_message(
            message.chat.id,
            "⏳ *RESELLER PAYMENT SUBMITTED SUCCESSFULLY!*\n"
            "AAPKA UTR ADMIN KE PAAS APPROVAL KE LIYE BHEJ DIYA GAYA HAI.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )

        markup = types.InlineKeyboardMarkup(
            row_width=2
        )

        markup.add(
            types.InlineKeyboardButton(
                "✅ APPROVE",
                callback_data=f"adm_app_res_{order_id}"
            ),
            types.InlineKeyboardButton(
                "❌ REJECT",
                callback_data=f"adm_rej_res_{order_id}"
            ),
        )

        admin_text = (
            f"⭐ *NEW RESELLER APPROVAL REQUEST!*\n\n"
            f"👤 *USER ID:* `{user_id}`\n"
            f"💵 *AMOUNT:* ₹{amount}\n"
            f"💳 *UTR NUMBER:* `{utr}`"
        )

        try:

            bot.send_message(
                ADMIN_ID,
                admin_text,
                parse_mode="Markdown",
                reply_markup=markup
            )

        except Exception:
            pass


# ============================================================
# ADMIN APPROVAL CALLBACK
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("adm_")
)
def admin_approval_callback(call):

    data = call.data

    parts = data.split("_")

    action = parts[1]

    target_type = parts[2]

    order_id = int(parts[3])

    # ========================================================
    # PLAN
    # ========================================================

    if target_type == "plan":

        row = orders_collection.find_one(
            {"id": order_id}
        )

        if not row:

            bot.answer_callback_query(
                call.id,
                "ORDER NOT FOUND!"
            )

            return

        user_id = row["user_id"]

        utr = row["utr"]

        duration = row["duration"]

        amount = row["amount"]

        status = row["status"]

        if status not in [
            "pending",
            "pending_admin"
        ]:

            bot.answer_callback_query(
                call.id,
                f"ORDER IS ALREADY {status.upper()}!",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # APPROVE PLAN
        # ----------------------------------------------------

        if action == "app":

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
                    "❌ OUT OF STOCK! ISS DURATION KI KEYS KHATAM HO GAYI HAIN.",
                    show_alert=True
                )

                return

            key_id = key_row["id"]

            license_key = key_row["license_key"]

            # Atomic key assignment
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
                    "❌ KEY ALREADY TAKEN. PLEASE TRY AGAIN.",
                    show_alert=True
                )

                return

            orders_collection.update_one(
                {"id": order_id},
                {
                    "$set": {
                        "status": "approved"
                    }
                }
            )

            bot.answer_callback_query(
                call.id,
                "ORDER APPROVED SUCCESSFULLY!"
            )

            try:

                bot.edit_message_text(
                    f"✅ *APPROVED BY ADMIN*\n\n"
                    f"👤 USER: `{user_id}`\n"
                    f"⏱ PLAN: {duration}\n"
                    f"💳 UTR: `{utr}`\n"
                    f"🔑 KEY: `{license_key}`",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

            except Exception:
                pass

            try:

                bot.send_message(
                    user_id,
                    f"🎉 *PAYMENT VERIFIED & APPROVED BY ADMIN!*\n\n"
                    f"• *PLAN:* {duration}\n"
                    f"• *YOUR LICENSE KEY:*\n"
                    f"`{license_key}`",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard(user_id),
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # REJECT PLAN
        # ----------------------------------------------------

        else:

            orders_collection.update_one(
                {"id": order_id},
                {
                    "$set": {
                        "status": "rejected"
                    }
                }
            )

            bot.answer_callback_query(
                call.id,
                "ORDER REJECTED."
            )

            try:

                bot.edit_message_text(
                    f"❌ *REJECTED BY ADMIN*\n\n"
                    f"👤 USER: `{user_id}`\n"
                    f"💳 UTR: `{utr}`",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

            except Exception:
                pass

            try:

                bot.send_message(
                    user_id,
                    "❌ PAYMENT NOT RECEIVED — APPROVAL REJECTED.\n"
                    "💳 PLEASE COMPLETE PAYMENT & SEND UTR.",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard(user_id),
                )

            except Exception:
                pass

    # ========================================================
    # RESELLER
    # ========================================================

    else:

        row = reseller_orders_collection.find_one(
            {"id": order_id}
        )

        if not row:

            bot.answer_callback_query(
                call.id,
                "ORDER NOT FOUND!"
            )

            return

        user_id = row["user_id"]

        utr = row["utr"]

        amount = row["amount"]

        status = row["status"]

        if status not in [
            "pending",
            "pending_admin"
        ]:

            bot.answer_callback_query(
                call.id,
                f"ORDER IS ALREADY {status.upper()}!",
                show_alert=True
            )

            return

        # ----------------------------------------------------
        # APPROVE RESELLER
        # ----------------------------------------------------

        if action == "app":

            reseller_orders_collection.update_one(
                {"id": order_id},
                {
                    "$set": {
                        "status": "approved"
                    }
                }
            )

            resellers_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "user_id": user_id
                    }
                },
                upsert=True
            )

            bot.answer_callback_query(
                call.id,
                "RESELLER ORDER APPROVED!"
            )

            try:

                bot.edit_message_text(
                    f"✅ *RESELLER APPROVED BY ADMIN*\n\n"
                    f"👤 USER: `{user_id}`\n"
                    f"💳 UTR: `{utr}`",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

            except Exception:
                pass

            try:

                bot.send_message(
                    user_id,
                    "🎉 *RESELLER SHIP APPROVED!*\n"
                    "YOUR RESELLER SHIP HAS BEEN ACTIVATED FOR 1 MONTH!",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard(user_id),
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # REJECT RESELLER
        # ----------------------------------------------------

        else:

            reseller_orders_collection.update_one(
                {"id": order_id},
                {
                    "$set": {
                        "status": "rejected"
                    }
                }
            )

            bot.answer_callback_query(
                call.id,
                "RESELLER ORDER REJECTED."
            )

            try:

                bot.edit_message_text(
                    f"❌ *RESELLER REJECTED BY ADMIN*\n\n"
                    f"👤 USER: `{user_id}`\n"
                    f"💳 UTR: `{utr}`",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                )

            except Exception:
                pass

            try:

                bot.send_message(
                    user_id,
                    "❌ PAYMENT NOT RECEIVED — APPROVAL REJECTED.",
                    parse_mode="Markdown",
                    reply_markup=get_main_reply_keyboard(user_id),
                )

            except Exception:
                pass


# ============================================================
# CANCEL ORDER
# ============================================================

@bot.message_handler(
    func=lambda message:
        "ORDER CANCEL" in (message.text or "").upper()
)
def handle_cancel_button(message):

    user_id = message.from_user.id

    if user_id not in user_states:

        bot.send_message(
            message.chat.id,
            "❌ ACTION CANCELLED.",
            reply_markup=get_main_reply_keyboard(user_id),
        )

        return

    state = user_states[user_id]

    order_id = state["order_id"]

    action_type = state["type"]

    if "qr_msg_id" in state:

        try:

            bot.delete_message(
                message.chat.id,
                state["qr_msg_id"]
            )

        except Exception:
            pass

    if action_type == "plan":

        orders_collection.delete_one(
            {"id": order_id}
        )

    else:

        reseller_orders_collection.delete_one(
            {"id": order_id}
        )

    del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "❌ PAYMENT CANCELLED SUCCESSFULLY.",
        reply_markup=get_main_reply_keyboard(user_id),
    )


# ============================================================
# RESET KEY
# ============================================================

@bot.callback_query_handler(
    func=lambda call:
        call.data.startswith("reset_")
)
def handle_reset_key(call):

    key_id = call.data.split("_")[1]

    user_id = call.from_user.id

    bot.answer_callback_query(
        call.id,
        "🔄 RESET REQUEST SENT TO OWNER/ADMIN SUCCESSFULLY!",
        show_alert=True,
    )

    bot.send_message(
        ADMIN_ID,
        f"⚠ *KEY RESET REQUEST*\n"
        f"USER ID: `{user_id}` "
        f"REQUESTED RESET FOR KEY ID: `{key_id}`",
        parse_mode="Markdown",
    )


# ============================================================
# CATCH-ALL: FORWARD USER MESSAGES TO ADMIN
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id != ADMIN_ID,
    content_types=[
        "text",
        "photo",
        "document",
        "video",
        "audio",
        "voice"
    ],
)
def forward_user_messages_to_admin(message):

    try:

        user = message.from_user

        username = (
            f"@{user.username}"
            if user.username
            else "No Username"
        )

        first_name = (
            user.first_name
            if user.first_name
            else "User"
        )

        info_text = (
            f"📩 *NEW MESSAGE FROM USER*\n"
            f"👤 Name: {first_name}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"🔗 Username: {username}"
        )

        sent_info = bot.send_message(
            ADMIN_ID,
            info_text,
            parse_mode="Markdown"
        )

        sent_forward = bot.forward_message(
            ADMIN_ID,
            message.chat.id,
            message.id
        )

        admin_reply_map[
            sent_info.message_id
        ] = user.id

        admin_reply_map[
            sent_forward.message_id
        ] = user.id

    except Exception as e:

        print(
            f"Error forwarding message to admin: {e}"
        )


# ============================================================
# ADMIN REPLY TO USER
# ============================================================

@bot.message_handler(
    func=lambda message:
        message.from_user.id == ADMIN_ID
        and message.reply_to_message is not None,
    content_types=[
        "text",
        "photo",
        "document",
        "video",
        "audio",
        "voice"
    ],
)
def handle_admin_reply(message):

    reply_msg = message.reply_to_message

    target_user_id = admin_reply_map.get(
        reply_msg.message_id
    )

    if not target_user_id:

        text_content = (
            reply_msg.text
            or reply_msg.caption
            or ""
        )

        match = re.search(
            r"User ID:\s*`?(\d+)`?",
            text_content
        )

        if match:

            target_user_id = int(
                match.group(1)
            )

        elif reply_msg.forward_from:

            target_user_id = (
                reply_msg.forward_from.id
            )

    if target_user_id:

        try:

            bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
            )

            bot.reply_to(
                message,
                "✅ *Reply successfully sent to user!*",
                parse_mode="Markdown",
            )

        except Exception as e:

            bot.reply_to(
                message,
                f"❌ Failed to send reply: `{e}`",
                parse_mode="Markdown"
            )

    else:

        bot.reply_to(
            message,
            "❌ Target user ID nahi mila. "
            "Kripya user ke **Info Message** par reply karein.",
            parse_mode="Markdown",
        )


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "BOT IS ACTIVE AND RUNNING SMOOTHLY WITH MONGODB!"


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
# START BOT
# ============================================================

if __name__ == "__main__":

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
        "Bot is running with Flask + MongoDB on Render..."
    )

    bot.infinity_polling(
        timeout=60,
        long_polling_timeout=60
    )
