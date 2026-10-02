import os
import re
import sqlite3
import threading
import time
import urllib.parse
from flask import Flask
import telebot
from telebot import types

# --- CONFIGURATION ---
# --- CONFIGURATION ---
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

ADMIN_ID = 6795305850
UPI_ID = "8905094188@ybl"
UPI_NAME = "NEXA CYBER"
OWNER_USERNAME = "R2FSUNILYT"
SETUP_CHANNEL_URL = "https://t.me/VoltageLoader"

bot = telebot.TeleBot(TOKEN)


# --- DATABASE SETUP ---
def init_db():
  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""CREATE TABLE IF NOT EXISTS keys_table (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        duration TEXT,
                        license_key TEXT UNIQUE,
                        status TEXT DEFAULT 'unused',
                        assigned_to INTEGER DEFAULT NULL)""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        utr TEXT,
                        duration TEXT,
                        amount INTEGER,
                        created_at REAL,
                        status TEXT DEFAULT 'pending')""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS reseller_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        utr TEXT,
                        amount INTEGER,
                        created_at REAL,
                        status TEXT DEFAULT 'pending')""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS resellers (
                        user_id INTEGER PRIMARY KEY)""")
  conn.commit()
  conn.close()


init_db()

# User state tracking dictionary & Admin reply map
user_states = {}
admin_reply_map = {}


# --- BACKGROUND WORKER: SEND TIMEOUT MESSAGE AFTER 5 MINS ---
def send_timeout_failed_message(chat_id, user_id, order_id, action_type="plan"):
  time.sleep(300)  # 5 Minutes

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "plan":
    cursor.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
  else:
    cursor.execute(
        "SELECT status FROM reseller_orders WHERE id = ?", (order_id,)
    )
    row = cursor.fetchone()
  conn.close()

  if row and row[0] in ["pending", "pending_admin"]:
    try:
      bot.send_message(
          chat_id,
          "⏳ PAYMENT TIME EXPIRED\n❌ APPROVAL REQUEST CLOSED\n📩 TRY AGAIN —"
          f" CONTACT: @{OWNER_USERNAME}",
          parse_mode="Markdown",
          reply_markup=get_main_reply_keyboard(user_id),
      )
    except Exception:
      pass


# --- KEYBOARDS ---
def get_main_reply_keyboard(user_id=None):
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  markup.add(
      types.KeyboardButton("🛒 PURCHASE KEY"), types.KeyboardButton("🔐 MY KEYS")
  )
  markup.add(types.KeyboardButton("🤝 BUY RESELLERSHIP"))
  markup.add(
      types.KeyboardButton("♻️️ SETUP CHANNEL"),
      types.KeyboardButton("💬 CONTACT SUPPORT"),
  )
  if user_id == ADMIN_ID:
    markup.add(types.KeyboardButton("👑 SUPER ADMIN"))
  return markup


def get_back_reply_keyboard():
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
  markup.add(types.KeyboardButton("🔚 BACK"))
  return markup


def get_payment_reply_keyboard():
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  markup.add(
      types.KeyboardButton("✅ PAYMENT DONE"),
      types.KeyboardButton("❌ ORDER CANCEL"),
  )
  return markup


# --- START COMMAND ---
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


# --- BACK BUTTON HANDLER ---
@bot.message_handler(func=lambda message: message.text == "🔚 BACK")
def handle_back_button(message):
  user_id = message.from_user.id
  if user_id in user_states:
    if "qr_msg_id" in user_states[user_id]:
      try:
        bot.delete_message(message.chat.id, user_states[user_id]["qr_msg_id"])
      except Exception:
        pass
    del user_states[user_id]

  bot.send_message(
      message.chat.id,
      "🏠 *MAIN MENU:*",
      parse_mode="Markdown",
      reply_markup=get_main_reply_keyboard(user_id),
  )


# --- SUPER ADMIN PANEL HANDLER ---
@bot.message_handler(func=lambda message: message.text == "👑 SUPER ADMIN")
def super_admin_panel(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "❌ YOU ARE NOT AUTHORIZED!")
    return

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      types.InlineKeyboardButton("➕ ADD SINGLE KEY", callback_data="sa_add_single"),
      types.InlineKeyboardButton("📦 ADD BULK KEY", callback_data="sa_add_bulk"),
      types.InlineKeyboardButton("❌ DELETE SINGLE KEY", callback_data="sa_del_single"),
      types.InlineKeyboardButton("🗑️ DELETE BULK KEYS", callback_data="sa_del_bulk"),
      types.InlineKeyboardButton("📋 SHOW ALL KEYS", callback_data="sa_show_keys"),
  )
  bot.send_message(
      message.chat.id,
      "👑 *SUPER ADMIN PANEL*\n\nNiche diye gaye options mein se select karein:",
      parse_mode="Markdown",
      reply_markup=markup,
  )


# --- SUPER ADMIN CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("sa_"))
def super_admin_callbacks(call):
  if call.from_user.id != ADMIN_ID:
    bot.answer_callback_query(call.id, "❌ Unauthorized!", show_alert=True)
    return

  data = call.data

  # --- ADD SINGLE FLOW ---
  if data == "sa_add_single":
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    durations = ["5 Hour", "1 Day", "2 Day", "3 Day", "7 Day", "30 Day"]
    for d in durations:
      cb_val = d.replace(" ", "_")
      markup.add(types.InlineKeyboardButton(f"⏱ {d}", callback_data=f"sa_sdur_{cb_val}"))
    bot.edit_message_text(
        "➕ *ADD SINGLE KEY*\n\nDuration select karein:",
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
        f"➕ *ADD SINGLE KEY*\n\nDuration: *{duration}*\n\n💬 Ab apni **License Key** yahan chat mein send karein:",
        parse_mode="Markdown",
    )

  # --- ADD BULK FLOW ---
  elif data == "sa_add_bulk":
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    durations = ["5 Hour", "1 Day", "2 Day", "3 Day", "7 Day", "30 Day"]
    for d in durations:
      cb_val = d.replace(" ", "_")
      markup.add(types.InlineKeyboardButton(f"⏱ {d}", callback_data=f"sa_bdur_{cb_val}"))
    bot.edit_message_text(
        "📦 *ADD BULK KEYS*\n\nDuration select karein:",
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
        f"📦 *ADD BULK KEYS*\n\nDuration: *{duration}*\n\n💬 Ab multiple keys **ek line mein ek key** karke yahan paste/send karein:",
        parse_mode="Markdown",
    )

  # --- DELETE SINGLE FLOW ---
  elif data == "sa_del_single":
    bot.answer_callback_query(call.id)
    user_states[ADMIN_ID] = {"type": "waiting_del_id"}
    bot.send_message(
        call.message.chat.id,
        "❌ *DELETE SINGLE KEY*\n\n💬 Jis key ko delete karna hai uska **Key ID** yahan send karein:",
        parse_mode="Markdown",
    )

  # --- DELETE BULK FLOW ---
  elif data == "sa_del_bulk":
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 PASTE KEYS TO DELETE IN BULK", callback_data="sa_del_paste_bulk"),
        types.InlineKeyboardButton("🗑️ DELETE ALL UNUSED KEYS", callback_data="sa_del_all_unused"),
    )
    bot.edit_message_text(
        "🗑️ *DELETE BULK OPTIONS*\n\nOption select karein:",
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
        "🗑 *DELETE BULK KEYS BY LIST*\n\n💬 Jin keys ko delete karna hai unhe **ek line mein ek key** karke yahan send karein:",
        parse_mode="Markdown",
    )

  elif data == "sa_del_all_unused":
    bot.answer_callback_query(call.id)
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keys_table WHERE status = 'unused'")
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    bot.send_message(
        call.message.chat.id,
        f"✅ Saari unused keys successfully delete kar di gayi hain! (Total deleted: `{deleted_count}`)",
        parse_mode="Markdown",
    )

  # --- SHOW ALL KEYS ---
  elif data == "sa_show_keys":
    bot.answer_callback_query(call.id)
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, duration, license_key, status, assigned_to FROM keys_table ORDER BY id DESC LIMIT 50")
    keys = cursor.fetchall()
    conn.close()

    if not keys:
      bot.send_message(call.message.chat.id, "❌ Database mein koi keys available nahi hain.")
      return

    text = "📋 *ALL STORED KEYS (Last 50):*\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    for kid, duration, lkey, status, assigned_to in keys:
      status_icon = "🟢 Unused" if status == 'unused' else f"🔴 Used (User: {assigned_to})"
      text += f"🆔 ID: `{kid}` | *{duration}*\n🔑 `{lkey}`\nStatus: {status_icon}\n\n"
      markup.add(
          types.InlineKeyboardButton(f"🗑️ Delete ID {kid}", callback_data=f"sa_del_id_{kid}")
      )

    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode="Markdown",
        reply_markup=markup,
    )

  elif data.startswith("sa_del_id_"):
    kid = int(data.split("_")[3])
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keys_table WHERE id = ?", (kid,))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, f"✅ Key ID {kid} deleted successfully!", show_alert=True)
    try:
      bot.edit_message_text(
          f"✅ *Key ID `{kid}` Successfully Deleted!*",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
      )
    except Exception:
      pass


# --- ADMIN STATE INPUT HANDLER ---
@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.from_user.id in user_states
    and user_states[message.from_user.id]["type"] in [
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
  text = message.text.strip()

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

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "waiting_single_key":
    duration = state["duration"]
    license_key = text

    try:
      cursor.execute(
          "INSERT INTO keys_table (duration, license_key, status) VALUES (?, ?, 'unused')",
          (duration, license_key),
      )
      conn.commit()
      conn.close()
      del user_states[user_id]
      bot.reply_to(
          message,
          f"✅ *SINGLE KEY ADDED SUCCESSFULLY!*\n\n• *DURATION:* {duration}\n• *KEY:* `{license_key}`",
          parse_mode="Markdown",
      )
    except sqlite3.IntegrityError:
      conn.close()
      bot.reply_to(
          message,
          "❌ *DUPLICATE KEY ERROR!*\nYeh license key pehle se database mein mojood hai.",
          parse_mode="Markdown",
      )

  elif action_type == "waiting_bulk_keys":
    duration = state["duration"]

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
      conn.close()
      bot.reply_to(message, "❌ Koi keys nahi mili!")
      return

    added_count = 0
    duplicate_count = 0

    for key in lines:
      try:
        cursor.execute(
            "INSERT INTO keys_table (duration, license_key, status) VALUES (?, ?, 'unused')",
            (duration, key),
        )
        added_count += 1
      except sqlite3.IntegrityError:
        duplicate_count += 1

    conn.commit()
    conn.close()
    del user_states[user_id]

    bot.reply_to(
        message,
        f"📦 *BULK KEYS ADDED REPORT*\n\n• *DURATION:* {duration}\n• *Successfully Added:* `{added_count}`\n• *Exact Duplicates Skipped:* `{duplicate_count}`",
        parse_mode="Markdown",
    )

  elif action_type == "waiting_del_id":
    try:
      key_id = int(text)
      cursor.execute("DELETE FROM keys_table WHERE id = ?", (key_id,))
      conn.commit()
      conn.close()
      del user_states[user_id]
      bot.reply_to(
          message,
          f"✅ Key ID `{key_id}` successfully delete kar di gayi hai!",
          parse_mode="Markdown",
      )
    except Exception:
      conn.close()
      bot.reply_to(
          message,
          "❌ Sahi Key ID enter karein (Sirf number hona chahiye).",
          parse_mode="Markdown",
      )

  elif action_type == "waiting_bulk_del":
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
      conn.close()
      bot.reply_to(message, "❌ Koi keys nahi mili!")
      return

    deleted_count = 0
    for key in lines:
      cursor.execute("DELETE FROM keys_table WHERE license_key = ?", (key,))
      deleted_count += cursor.rowcount

    conn.commit()
    conn.close()
    del user_states[user_id]

    bot.reply_to(
        message,
        f"🗑️ *BULK DELETE REPORT*\n\n• *Total Keys Deleted:* `{deleted_count}`",
        parse_mode="Markdown",
    )


# --- REPLY MENU HANDLERS ---
@bot.message_handler(
    func=lambda message: message.text in [
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

  if message.text == "🛒 PURCHASE KEY":
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()

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
      cursor.execute(
          "SELECT COUNT(*) FROM keys_table WHERE duration = ? AND status = 'unused'",
          (duration,),
      )
      stock_count = cursor.fetchone()[0]
      button_title = f"{title} | STOCK: {stock_count}"
      cb_duration = duration.replace(" ", "_")
      markup.add(
          types.InlineKeyboardButton(
              button_title, callback_data=f"plan_{cb_duration}_{amount}"
          )
      )

    conn.close()

    bot.send_message(
        message.chat.id,
        "📋 *SELECT PLAN*\n\nAPNA PLAN SELECT KAREIN:",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    bot.send_message(
        message.chat.id,
        "👇 PICHE JAANE KE LIYE NICHE **🔚 BACK** DABAYEIN:",
        reply_markup=get_back_reply_keyboard(),
    )

  elif message.text == "🔐 MY KEYS":
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, duration, license_key FROM keys_table WHERE status = 'used' AND assigned_to = ?",
        (user_id,),
    )
    keys = cursor.fetchall()
    conn.close()

    if not keys:
      bot.send_message(
          message.chat.id,
          "❌ AAPKE PAAS KOI ACTIVE KEY NAHI HAI!",
          parse_mode="Markdown",
      )
      return

    markup = types.InlineKeyboardMarkup(row_width=1)
    text = "🔐 *YOUR PURCHASED KEYS:*\n\n"
    for key_id, duration, key in keys:
      text += f"• *Plan:* ({duration})\n🔑 `{key}`\n\n"
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

  elif message.text == "🤝 BUY RESELLERSHIP":
    amount = 1599
    current_time = time.time()

    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reseller_orders (user_id, utr, amount, created_at, status) VALUES (?, '', ?, ?, 'pending')",
        (user_id, amount, current_time),
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    unique_tr = f"R2FRES{order_id}{int(current_time)}"
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

    caption_text = (
        "💳 *SCAN & PAY*\n\n"
        "• *LOADER:* RESELLER SHIP (1 MONTH)\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
        "1️⃣ PEHLE PAYMENT KAREIN.\n"
        "2️⃣ **12-DIGIT UTR** AUR **PAYMENT SCREENSHOT** DONO YAHIN CHAT MEIN SEND KAREIN.\n"
        "3️⃣ SEND KARNE KE BAAD NICHE MENU MEIN **✅ PAYMENT DONE** PAR CLICK KAREIN."
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
        args=(message.chat.id, user_id, order_id, "reseller"),
        daemon=True,
    ).start()

  elif message.text == "♻️ SETUP CHANNEL":
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "🔗 OPEN SETUP CHANNEL", url=SETUP_CHANNEL_URL
        )
    )
    bot.send_message(
        message.chat.id,
        "♻️ *CLICK THE BUTTON BELOW TO OPEN SETUP CHANNEL:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )

  elif message.text == "💬 CONTACT SUPPORT":
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "💬 OPEN SUPPORT CHAT", url=f"https://t.me/{OWNER_USERNAME}"
        )
    )
    bot.send_message(
        message.chat.id,
        "💬 *CLICK THE BUTTON BELOW TO CONTACT SUPPORT:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# --- HANDLE PLAN & QR ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def handle_plan(call):
  bot.answer_callback_query(call.id)
  parts = call.data.split("_")
  amount = int(parts[-1])
  duration = "_".join(parts[1:-1]).replace("_", " ")
  user_id = call.from_user.id
  current_time = time.time()

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO orders (user_id, utr, duration, amount, created_at, status) VALUES (?, '', ?, ?, ?, 'pending')",
      (user_id, duration, amount, current_time),
  )
  order_id = cursor.lastrowid
  conn.commit()
  conn.close()

  unique_tr = f"R2F{order_id}{int(current_time)}"
  upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
  qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

  caption_text = (
      "💳 *SCAN & PAY*\n\n"
      f"• *PLAN:* {duration}\n"
      f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
      f"• *UPI ID:* `{UPI_ID}`\n\n"
      "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
      "1️⃣ PEHLE PAYMENT KAREIN.\n"
      "2️⃣ **12-DIGIT UTR** AUR **PAYMENT SCREENSHOT** DONO YAHIN CHAT MEIN SEND KAREIN.\n"
      "3️⃣ SEND KARNE KE BAAD NICHE MENU MEIN **✅ PAYMENT DONE** PAR CLICK KAREIN."
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
      args=(call.message.chat.id, user_id, order_id, "plan"),
      daemon=True,
  ).start()


# --- HANDLE UTR TEXT & SCREENSHOT INPUT ---
@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id]["type"] in ["plan", "reseller"],
    content_types=["text", "photo"],
)
def handle_utr_text(message):
  user_id = message.from_user.id
  state = user_states[user_id]

  # If user sends a photo (Screenshot)
  if message.photo:
    caption = message.caption or ""
    match = re.search(r"\b\d{12}\b", caption)
    if match:
      utr = match.group(0)
    else:
      bot.reply_to(
          message,
          "📸 *Screenshot Mil Gaya!*\nAb apna **12-digit UTR number** bhi yahin chat mein text karke bhej dein:",
          parse_mode="Markdown",
          reply_markup=get_payment_reply_keyboard(),
      )
      return
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
      else:
        handle_reply_menu(message)
      return

    raw_text = text.strip()
    match = re.search(r"\b\d{12}\b", raw_text)
    if match:
      utr = match.group(0)
    else:
      cleaned = "".join(filter(str.isdigit, raw_text))
      if len(cleaned) == 12:
        utr = cleaned
      else:
        bot.reply_to(
            message,
            "❌ *INVALID UTR FORMAT!*\nKRIPYA APNA **12-DIGIT NUMERIC UTR** DOBARA BHEJEIN:",
            parse_mode="Markdown",
            reply_markup=get_payment_reply_keyboard(),
        )
        return

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT id FROM orders WHERE utr = ? AND status = 'approved'", (utr,)
  )
  used_in_orders = cursor.fetchone()
  cursor.execute(
      "SELECT id FROM reseller_orders WHERE utr = ? AND status = 'approved'",
      (utr,),
  )
  used_in_resellers = cursor.fetchone()
  conn.close()

  if used_in_orders or used_in_resellers:
    bot.reply_to(
        message,
        "❌ *FRAUD ALERT!* YEH UTR NUMBER PEHLE HI USE KIYA JA CHUKA HAI.",
        parse_mode="Markdown",
        reply_markup=get_payment_reply_keyboard(),
    )
    return

  order_id = state["order_id"]
  action_type = state["type"]

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  if action_type == "plan":
    cursor.execute("UPDATE orders SET utr = ? WHERE id = ?", (utr, order_id))
  else:
    cursor.execute(
        "UPDATE reseller_orders SET utr = ? WHERE id = ?", (utr, order_id)
    )
  conn.commit()
  conn.close()

  bot.reply_to(
      message,
      "✅ *UTR VERIFIED & SAVED SUCCESSFULLY!*\nAb niche menu mein diye gaye **✅ PAYMENT DONE** button par click karein.",
      parse_mode="Markdown",
      reply_markup=get_payment_reply_keyboard(),
  )


# --- HANDLE PAYMENT DONE BUTTON ---
@bot.message_handler(
    func=lambda message: "PAYMENT DONE" in (message.text or "").upper()
)
def handle_payment_done_button(message):
  user_id = message.from_user.id

  if user_id not in user_states:
    bot.send_message(
        message.chat.id,
        "❌ KOI ACTIVE PAYMENT SESSION NAHI MILA. KRIPYA /start DABAYEIN.",
        reply_markup=get_main_reply_keyboard(user_id),
    )
    return

  state = user_states[user_id]

  if "qr_msg_id" in state:
    try:
      bot.delete_message(message.chat.id, state["qr_msg_id"])
    except Exception:
      pass

  order_id = state["order_id"]
  action_type = state["type"]

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "plan":
    cursor.execute(
        "SELECT utr, duration, amount FROM orders WHERE id = ?",
        (order_id,),
    )
    row = cursor.fetchone()
  else:
    cursor.execute(
        "SELECT utr, amount FROM reseller_orders WHERE id = ?", (order_id,)
    )
    row = cursor.fetchone()

  if not row or not row[0] or len(row[0]) != 12:
    conn.close()
    bot.send_message(
        message.chat.id,
        "❌ PEHLE APNA VALID 12-DIGIT UTR CHAT MEIN SEND KAREIN, FIR PAYMENT DONE DABAYEIN!",
        reply_markup=get_payment_reply_keyboard(),
    )
    return

  if action_type == "plan":
    utr, duration, amount = row

    cursor.execute(
        "UPDATE orders SET status = 'pending_admin' WHERE id = ?", (order_id,)
    )
    conn.commit()
    conn.close()

    del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "⏳ *PAYMENT SUBMITTED SUCCESSFULLY!*\nAAPKA UTR ADMIN KE PAAS APPROVAL KE LIYE BHEJ DIYA GAYA HAI.",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(user_id),
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "✅ APPROVE", callback_data=f"adm_app_plan_{order_id}"
        ),
        types.InlineKeyboardButton(
            "❌ REJECT", callback_data=f"adm_rej_plan_{order_id}"
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
          ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=markup
      )
    except Exception:
      pass

  else:
    utr, amount = row
    cursor.execute(
        "UPDATE reseller_orders SET status = 'pending_admin' WHERE id = ?",
        (order_id,),
    )
    conn.commit()
    conn.close()

    del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "⏳ *RESELLER PAYMENT SUBMITTED SUCCESSFULLY!*\nAAPKA UTR ADMIN KE PAAS APPROVAL KE LIYE BHEJ DIYA GAYA HAI.",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(user_id),
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "✅ APPROVE", callback_data=f"adm_app_res_{order_id}"
        ),
        types.InlineKeyboardButton(
            "❌ REJECT", callback_data=f"adm_rej_res_{order_id}"
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
          ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=markup
      )
    except Exception:
      pass


# --- ADMIN CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_approval_callback(call):
  data = call.data
  parts = data.split("_")
  action = parts[1]
  target_type = parts[2]
  order_id = int(parts[3])

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if target_type == "plan":
    cursor.execute(
        "SELECT user_id, utr, duration, amount, status FROM orders WHERE id = ?",
        (order_id,),
    )
    row = cursor.fetchone()
    if not row:
      conn.close()
      bot.answer_callback_query(call.id, "ORDER NOT FOUND!")
      return

    user_id, utr, duration, amount, status = row

    if status not in ["pending", "pending_admin"]:
      conn.close()
      bot.answer_callback_query(
          call.id, f"ORDER IS ALREADY {status.upper()}!", show_alert=True
      )
      return

    if action == "app":
      cursor.execute(
          "SELECT id, license_key FROM keys_table WHERE duration = ? AND status = 'unused' LIMIT 1",
          (duration,),
      )
      key_row = cursor.fetchone()

      if not key_row:
        conn.close()
        bot.answer_callback_query(
            call.id,
            "❌ OUT OF STOCK! ISS DURATION KI KEYS KHATAM HO GAYI HAIN.",
            show_alert=True,
        )
        return

      key_id = key_row[0]
      license_key = key_row[1]

      cursor.execute(
          "UPDATE keys_table SET status = 'used', assigned_to = ? WHERE id = ?",
          (user_id, key_id),
      )
      cursor.execute(
          "UPDATE orders SET status = 'approved' WHERE id = ?", (order_id,)
      )
      conn.commit()
      conn.close()

      bot.answer_callback_query(call.id, "ORDER APPROVED SUCCESSFULLY!")
      try:
        bot.edit_message_text(
            f"✅ *APPROVED BY ADMIN*\n\n👤 USER: `{user_id}`\n⏱ PLAN: {duration}\n💳 UTR: `{utr}`\n🔑 KEY: `{license_key}`",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
        )
      except Exception:
        pass

      try:
        bot.send_message(
            user_id,
            f"🎉 *PAYMENT VERIFIED & APPROVED BY ADMIN!*\n\n• *PLAN:* {duration}\n• *YOUR LICENSE KEY:*\n`{license_key}`",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )
      except Exception:
        pass

    else:
      cursor.execute(
          "UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,)
      )
      conn.commit()
      conn.close()

      bot.answer_callback_query(call.id, "ORDER REJECTED.")
      try:
        bot.edit_message_text(
            f"❌ *REJECTED BY ADMIN*\n\n👤 USER: `{user_id}`\n💳 UTR: `{utr}`",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
        )
      except Exception:
        pass

      try:
        bot.send_message(
            user_id,
            "❌ PAYMENT NOT RECEIVED — APPROVAL REJECTED.\n💳 PLEASE COMPLETE PAYMENT & SEND UTR.",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )
      except Exception:
        pass

  else:
    cursor.execute(
        "SELECT user_id, utr, amount, status FROM reseller_orders WHERE id = ?",
        (order_id,),
    )
    row = cursor.fetchone()
    if not row:
      conn.close()
      bot.answer_callback_query(call.id, "ORDER NOT FOUND!")
      return

    user_id, utr, amount, status = row

    if status not in ["pending", "pending_admin"]:
      conn.close()
      bot.answer_callback_query(
          call.id, f"ORDER IS ALREADY {status.upper()}!", show_alert=True
      )
      return

    if action == "app":
      cursor.execute(
          "UPDATE reseller_orders SET status = 'approved' WHERE id = ?",
          (order_id,),
      )
      cursor.execute(
          "INSERT OR IGNORE INTO resellers (user_id) VALUES (?)", (user_id,)
      )
      conn.commit()
      conn.close()

      bot.answer_callback_query(call.id, "RESELLER ORDER APPROVED!")
      try:
        bot.edit_message_text(
            f"✅ *RESELLER APPROVED BY ADMIN*\n\n👤 USER: `{user_id}`\n💳 UTR: `{utr}`",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
        )
      except Exception:
        pass

      try:
        bot.send_message(
            user_id,
            "🎉 *RESELLER SHIP APPROVED!*\nYOUR RESELLER SHIP HAS BEEN ACTIVATED FOR 1 MONTH!",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )
      except Exception:
        pass

    else:
      cursor.execute(
          "UPDATE reseller_orders SET status = 'rejected' WHERE id = ?",
          (order_id,),
      )
      conn.commit()
      conn.close()

      bot.answer_callback_query(call.id, "RESELLER ORDER REJECTED.")
      try:
        bot.edit_message_text(
            f"❌ *RESELLER REJECTED BY ADMIN*\n\n👤 USER: `{user_id}`\n💳 UTR: `{utr}`",
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


# --- CANCEL ORDER ---
@bot.message_handler(
    func=lambda message: "ORDER CANCEL" in (message.text or "").upper()
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
      bot.delete_message(message.chat.id, state["qr_msg_id"])
    except Exception:
      pass

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  if action_type == "plan":
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
  else:
    cursor.execute("DELETE FROM reseller_orders WHERE id = ?", (order_id,))
  conn.commit()
  conn.close()

  del user_states[user_id]

  bot.send_message(
      message.chat.id,
      "❌ PAYMENT CANCELLED SUCCESSFULLY.",
      reply_markup=get_main_reply_keyboard(user_id),
  )


# --- RESET KEY HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("reset_"))
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
      f"⚠ *KEY RESET REQUEST*\nUSER ID: `{user_id}` REQUESTED RESET FOR KEY ID: `{key_id}`",
      parse_mode="Markdown",
  )


# --- CATCH-ALL: FORWARD USER MESSAGES TO ADMIN ---
@bot.message_handler(
    func=lambda message: message.from_user.id != ADMIN_ID,
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def forward_user_messages_to_admin(message):
  try:
    user = message.from_user
    username = f"@{user.username}" if user.username else "No Username"
    first_name = user.first_name if user.first_name else "User"

    info_text = (
        f"📩 *NEW MESSAGE FROM USER*\n"
        f"👤 Name: {first_name}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🔗 Username: {username}"
    )
    sent_info = bot.send_message(ADMIN_ID, info_text, parse_mode="Markdown")
    sent_forward = bot.forward_message(ADMIN_ID, message.chat.id, message.id)

    # Save mapping so admin can reply
    admin_reply_map[sent_info.message_id] = user.id
    admin_reply_map[sent_forward.message_id] = user.id
  except Exception as e:
    print(f"Error forwarding message to admin: {e}")


# --- ADMIN REPLY TO USER HANDLER ---
@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.reply_to_message is not None,
    content_types=["text", "photo", "document", "video", "audio", "voice"],
)
def handle_admin_reply(message):
  reply_msg = message.reply_to_message
  target_user_id = admin_reply_map.get(reply_msg.message_id)

  if not target_user_id:
    text_content = reply_msg.text or reply_msg.caption or ""
    match = re.search(r"User ID:\s*`?(\d+)`?", text_content)
    if match:
      target_user_id = int(match.group(1))
    elif reply_msg.forward_from:
      target_user_id = reply_msg.forward_from.id

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
      bot.reply_to(message, f"❌ Failed to send reply: `{e}`", parse_mode="Markdown")
  else:
    bot.reply_to(
        message,
        "❌ Target user ID nahi mila. Kripya user ke **Info Message** par reply karein.",
        parse_mode="Markdown",
    )


# --- FLASK SERVER & BOT RUNNER ---
app = Flask(__name__)


@app.route("/")
def home():
  return "BOT IS ACTIVE AND RUNNING SMOOTHLY!"


def run_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
  threading.Thread(target=run_flask, daemon=True).start()

  try:
    bot.remove_webhook()
    bot.delete_webhook(drop_pending_updates=True)
  except Exception:
    pass

  print("Bot is running with Flask web server on Render...")
  bot.infinity_polling(timeout=60, long_polling_timeout=60)
