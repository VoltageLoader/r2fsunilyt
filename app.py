import sqlite3
import threading
import time
import urllib.parse
import telebot
from telebot import types

# --- CONFIGURATION ---
TOKEN = "8052389503:AAG8O3ZH4NCJJrW7erp4u9W3IfKm4z18itk"
ADMIN_ID = 6795305850
UPI_ID = "8905094188@ybl"
UPI_NAME = "Nexa Cyber"
OWNER_USERNAME = "R2FSUNILYT"
SETUP_CHANNEL_URL = "https://t.me/VoltageLoader"

bot = telebot.TeleBot(TOKEN)


# --- DATABASE SETUP ---
def init_db():
  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("""CREATE TABLE IF NOT EXISTS keys_table (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        loader TEXT,
                        duration TEXT,
                        license_key TEXT,
                        status TEXT DEFAULT 'unused',
                        assigned_to INTEGER DEFAULT NULL)""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        utr TEXT,
                        loader TEXT,
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

# User state tracking dictionary
user_states = {}


# --- HELPER: GET LOADER DISPLAY NAME ---
def get_loader_display_name(loader_code):
  if loader_code == "NEXA":
    return "NICE X NEXA"
  return loader_code


# --- BACKGROUND WORKER: AUTO DELETE & EXPIRE QR AFTER 5 MINS ---
def expire_order_after_delay(
    chat_id, user_id, order_id, qr_msg_id, action_type="plan"
):
  time.sleep(300)  # Exactly 5 Minutes (300 seconds)

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "plan":
    cursor.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone()
    if row and row[0] == "pending":
      cursor.execute(
          "UPDATE orders SET status = 'expired' WHERE id = ?", (order_id,)
      )
      conn.commit()
  else:
    cursor.execute(
        "SELECT status FROM reseller_orders WHERE id = ?", (order_id,)
    )
    row = cursor.fetchone()
    if row and row[0] == "pending":
      cursor.execute(
          "UPDATE reseller_orders SET status = 'expired' WHERE id = ?",
          (order_id,),
      )
      conn.commit()
  conn.close()

  # Clear user state if active for this order
  if user_id in user_states and user_states[user_id].get("order_id") == order_id:
    del user_states[user_id]

  # Delete QR Code message automatically
  try:
    bot.delete_message(chat_id, qr_msg_id)
  except Exception:
    pass

  # Send expiration notification
  try:
    bot.send_message(
        chat_id,
        "❌ *QR Code Expired!*\n5 minute ka samay samapt ho gaya hai aur QR"
        " delete kar diya gaya hai. Kripya naya order banayein.",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )
  except Exception:
    pass


# --- REPLY KEYBOARD (MAIN MENU) ---
def get_main_reply_keyboard():
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  btn1 = types.KeyboardButton("🛒 PURCHASE KEY")
  btn2 = types.KeyboardButton("🔐 MY KEYS")
  btn3 = types.KeyboardButton("🤝 BUY RESELLERSHIP")
  btn4 = types.KeyboardButton("♻ SETUP CHANNEL")
  btn5 = types.KeyboardButton("💬 CONTACT SUPPORT")
  markup.add(btn1, btn2)
  markup.add(btn3)
  markup.add(btn4, btn5)
  return markup


# --- REPLY KEYBOARD (PAYMENT MENU - NEAR CHAT BAR) ---
def get_payment_reply_keyboard():
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  btn1 = types.KeyboardButton("✅ Payment Done")
  btn2 = types.KeyboardButton("❌ Order Cancel")
  markup.add(btn1, btn2)
  return markup


# --- CHECK IF USER IS ADMIN OR RESELLER ---
def is_admin_or_reseller(user_id):
  if user_id == ADMIN_ID:
    return True
  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM resellers WHERE user_id = ?", (user_id,))
  res = cursor.fetchone()
  conn.close()
  return res is not None


# --- MAIN MENU (/start) ---
@bot.message_handler(commands=["start"])
def send_welcome(message):
  if message.from_user.id in user_states:
    del user_states[message.from_user.id]

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
      reply_markup=get_main_reply_keyboard(),
  )


# --- REPLY MENU BUTTON HANDLERS ---
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
  if message.from_user.id in user_states:
    del user_states[message.from_user.id]

  if message.text == "🛒 PURCHASE KEY":
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "⚡ Voltage Loader", callback_data="loader_Voltage"
        ),
        types.InlineKeyboardButton(
            "🔥 NICE X NEXA", callback_data="loader_NEXA"
        ),
    )
    bot.send_message(
        message.chat.id,
        "📦 *Select Loader*\n\nApna pasandida loader select karein:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

  elif message.text == "🔐 MY KEYS":
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, loader, duration, license_key FROM keys_table WHERE status"
        " = 'used' AND assigned_to = ?",
        (user_id,),
    )
    keys = cursor.fetchall()
    conn.close()

    if not keys:
      bot.send_message(
          message.chat.id,
          "❌ Aapke paas koi active key nahi hai!",
          parse_mode="Markdown",
      )
      return

    markup = types.InlineKeyboardMarkup(row_width=1)
    text = "🔐 *Your Purchased Keys:*\n\n"
    for key_id, loader_code, duration, key in keys:
      loader_display = get_loader_display_name(loader_code)
      text += f"• *{loader_display}* ({duration})\n🔑 `{key}`\n\n"
      markup.add(
          types.InlineKeyboardButton(
              f"🔄 Reset Key ({loader_display} - {duration})",
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
    user_id = message.from_user.id

    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reseller_orders (user_id, utr, amount, created_at, status)"
        " VALUES (?, '', ?, ?, 'pending')",
        (user_id, amount, current_time),
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    unique_tr = f"R2FRES{order_id}{int(current_time)}"
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

    caption_text = (
        "💳 *SCAN & PAY (5 MINS EXPIRY)*\n\n"
        "• *LOADER:* Reseller Ship (1 Month)\n"
        "• *PLAN:* 30 Days\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
        "1️⃣ Pehle payment karein aur 12-digit UTR yahin chat mein **send"
        " karein**.\n"
        "2️⃣ UTR send karne ke baad niche menu mein **✅ Payment Done** par click"
        " karein.\n"
        "3️⃣ Cancel karne ke liye **❌ Order Cancel** dabayein."
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

    # Start 5-minute background expiry thread
    threading.Thread(
        target=expire_order_after_delay,
        args=(
            message.chat.id,
            user_id,
            order_id,
            sent_msg.message_id,
            "reseller",
        ),
        daemon=True,
    ).start()

  elif message.text == "♻️ SETUP CHANNEL":
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "🔗 Open Setup Channel", url=SETUP_CHANNEL_URL
        )
    )
    bot.send_message(
        message.chat.id,
        "♻️ *Click the button below to open Setup Channel:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )

  elif message.text == "💬 CONTACT SUPPORT":
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "💬 Open Support Chat", url=f"https://t.me/{OWNER_USERNAME}"
        )
    )
    bot.send_message(
        message.chat.id,
        "💬 *Click the button below to contact Support:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# --- SELECT PLANS FOR CHOSEN LOADER WITH LIVE STOCK ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("loader_"))
def select_plan(call):
  loader_code = call.data.split("_")[1]
  loader_display = get_loader_display_name(loader_code)

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  markup = types.InlineKeyboardMarkup(row_width=2)

  plans = [
      ("⏱ 5 Hour - ₹30", "5 Hour", 30),
      ("⏱️ 1 Day - ₹60", "1 Day", 60),
      ("⏱️ 2 Day - ₹100", "2 Day", 100),
      ("⏱️️ 3 Day - ₹180", "3 Day", 180),
      ("⏱ 7 Day - ₹399", "7 Day", 399),
      ("⏱️ 30 Day - ₹699", "30 Day", 699),
  ]

  for title, duration, amount in plans:
    cursor.execute(
        "SELECT COUNT(*) FROM keys_table WHERE duration = ? AND status = 'unused'",
        (duration,),
    )
    stock_count = cursor.fetchone()[0]
    button_title = f"{title} | Stock: {stock_count}"

    markup.add(
        types.InlineKeyboardButton(
            button_title, callback_data=f"plan_{loader_code}_{duration}_{amount}"
        )
    )

  conn.close()

  bot.edit_message_text(
      f"📋 *{loader_display} Plans*\n\nApna plan select karein:",
      call.message.chat.id,
      call.message.message_id,
      parse_mode="Markdown",
      reply_markup=markup,
  )


# --- DYNAMIC QR CODE GENERATOR FOR PLANS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def handle_plan(call):
  parts = call.data.split("_")
  loader_code = parts[1]
  duration = parts[2]
  amount = int(parts[3])
  loader_display = get_loader_display_name(loader_code)
  user_id = call.from_user.id
  current_time = time.time()

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO orders (user_id, utr, loader, duration, amount, created_at,"
      " status) VALUES (?, '', ?, ?, ?, ?, 'pending')",
      (user_id, loader_code, duration, amount, current_time),
  )
  order_id = cursor.lastrowid
  conn.commit()
  conn.close()

  unique_tr = f"R2F{order_id}{int(current_time)}"
  upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR&tr={unique_tr}"
  qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

  caption_text = (
      "💳 *SCAN & PAY (5 MINS EXPIRY)*\n\n"
      f"• *LOADER:* {loader_display}\n"
      f"• *PLAN:* {duration}\n"
      f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
      f"• *UPI ID:* `{UPI_ID}`\n\n"
      "⚠️ *IMPORTANT INSTRUCTIONS*\n\n"
      "1️⃣ Pehle payment karein aur 12-digit UTR yahin chat mein **send"
      " karein**.\n"
      "2️⃣ UTR send karne ke baad niche menu mein **✅ Payment Done** par click"
      " karein.\n"
      "3️⃣ Cancel karne ke liye **❌ Order Cancel** dabayein."
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
      "loader": loader_code,
      "duration": duration,
      "amount": amount,
      "timestamp": current_time,
      "qr_msg_id": sent_msg.message_id,
  }

  # Start 5-minute background expiry thread
  threading.Thread(
      target=expire_order_after_delay,
      args=(call.message.chat.id, user_id, order_id, sent_msg.message_id, "plan"),
      daemon=True,
  ).start()


# --- HANDLE PAYMENT DONE BUTTON FROM MENU ---
@bot.message_handler(func=lambda message: message.text == "✅ Payment Done")
def handle_payment_done_button(message):
  user_id = message.from_user.id

  if user_id not in user_states:
    bot.send_message(
        message.chat.id,
        "❌ Koi active payment session nahi mila. Kripya /start dabayein.",
        reply_markup=get_main_reply_keyboard(),
    )
    return

  state = user_states[user_id]

  # Delete QR code photo message
  if "qr_msg_id" in state:
    try:
      bot.delete_message(message.chat.id, state["qr_msg_id"])
    except Exception:
      pass

  if time.time() - state["timestamp"] > 300:
    del user_states[user_id]
    bot.send_message(
        message.chat.id,
        "❌ *QR Expired!* 5 minute ho chuke hain.",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )
    return

  order_id = state["order_id"]
  action_type = state["type"]

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "plan":
    cursor.execute(
        "SELECT utr, loader, duration, amount FROM orders WHERE id = ?",
        (order_id,),
    )
    row = cursor.fetchone()
  else:
    cursor.execute(
        "SELECT utr, amount FROM reseller_orders WHERE id = ?", (order_id,)
    )
    row = cursor.fetchone()

  if not row or not row[0] or row[0].strip() == "":
    conn.close()
    bot.send_message(
        message.chat.id,
        "❌ Pehle 12-digit UTR chat mein send karein, fir Payment Done dabayein!",
        reply_markup=get_payment_reply_keyboard(),
    )
    return

  if action_type == "plan":
    utr, loader_code, duration, amount = row
    loader_display = get_loader_display_name(loader_code)

    cursor.execute("UPDATE orders SET status = 'pending' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "⏳ UTR received! Verifying payment with admin. Please wait...",
        reply_markup=get_main_reply_keyboard(),
    )

    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    btn_approve = types.InlineKeyboardButton(
        "✅ Approve", callback_data=f"app_{order_id}_{user_id}"
    )
    btn_reject = types.InlineKeyboardButton(
        "❌ Reject", callback_data=f"rej_{order_id}_{user_id}"
    )
    admin_markup.add(btn_approve, btn_reject)

    admin_text = (
        f"🔔 *New Plan Payment Request!*\n\n"
        f"👤 *User ID:* `{user_id}`\n"
        f"📦 *Loader:* {loader_display} ({duration})\n"
        f"💵 *Amount:* ₹{amount}\n"
        f"💳 *UTR Number:* `{utr}`"
    )
    bot.send_message(
        ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup
    )

  else:
    utr, amount = row
    cursor.execute(
        "UPDATE reseller_orders SET status = 'pending' WHERE id = ?", (order_id,)
    )
    conn.commit()
    conn.close()

    del user_states[user_id]

    bot.send_message(
        message.chat.id,
        "⏳ Reseller UTR received! Admin verification in progress. Please wait...",
        reply_markup=get_main_reply_keyboard(),
    )

    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    btn_approve = types.InlineKeyboardButton(
        "✅ Approve Reseller", callback_data=f"resapp_{order_id}_{user_id}"
    )
    btn_reject = types.InlineKeyboardButton(
        "❌ Reject", callback_data=f"resrej_{order_id}_{user_id}"
    )
    admin_markup.add(btn_approve, btn_reject)

    admin_text = (
        f"⭐ *New Reseller Request!*\n\n"
        f"👤 *User ID:* `{user_id}`\n"
        f"💵 *Amount:* ₹{amount}\n"
        f"💳 *UTR Number:* `{utr}`"
    )
    bot.send_message(
        ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup
    )


# --- HANDLE ORDER CANCEL BUTTON FROM MENU ---
@bot.message_handler(func=lambda message: message.text == "❌ Order Cancel")
def handle_cancel_button(message):
  user_id = message.from_user.id

  if user_id not in user_states:
    bot.send_message(
        message.chat.id,
        "❌ Action cancelled.",
        reply_markup=get_main_reply_keyboard(),
    )
    return

  state = user_states[user_id]
  order_id = state["order_id"]
  action_type = state["type"]

  # Delete QR code photo message
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
      "❌ Payment cancelled successfully.",
      reply_markup=get_main_reply_keyboard(),
  )


# --- HANDLE UTR TEXT INPUT ---
@bot.message_handler(
    func=lambda message: message.from_user.id in user_states
    and user_states[message.from_user.id]["type"] in ["plan", "reseller"]
)
def handle_utr_text(message):
  user_id = message.from_user.id

  if message.text in [
      "🛒 PURCHASE KEY",
      "🔐 MY KEYS",
      "🤝 BUY RESELLERSHIP",
      "♻️ SETUP CHANNEL",
      "💬 CONTACT SUPPORT",
  ] or message.text.startswith("/"):
    if user_id in user_states and "qr_msg_id" in user_states[user_id]:
      try:
        bot.delete_message(message.chat.id, user_states[user_id]["qr_msg_id"])
      except Exception:
        pass
    del user_states[user_id]
    handle_reply_menu(message)
    return

  state = user_states[user_id]

  if time.time() - state["timestamp"] > 300:
    if "qr_msg_id" in state:
      try:
        bot.delete_message(message.chat.id, state["qr_msg_id"])
      except Exception:
        pass
    del user_states[user_id]
    bot.reply_to(
        message,
        "❌ *Payment QR Expired!*\n5 minute ka samay samapt ho gaya hai.",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(),
    )
    return

  utr = message.text.strip()
  if not utr.isalnum() or len(utr) < 8 or len(utr) > 25:
    bot.reply_to(
        message,
        "❌ *Invalid UTR/Transaction ID!*\nKripya sahi 12-digit UTR number bhejein:",
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
    cursor.execute("UPDATE reseller_orders SET utr = ? WHERE id = ?", (utr, order_id))
  conn.commit()
  conn.close()

  bot.reply_to(
      message,
      "✅ *UTR Saved Successfully!*\nAb niche menu mein diye gaye **✅ Payment Done** button par click karein.",
      parse_mode="Markdown",
      reply_markup=get_payment_reply_keyboard(),
  )


# --- ADMIN APPROVAL HANDLER ---
@bot.callback_query_handler(
    func=lambda call: call.data.startswith(("app_", "rej_", "resapp_", "resrej_"))
)
def handle_admin_action(call):
  data = call.data.split("_")
  action = data[0]
  order_id = data[1]
  user_id = int(data[2])

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action == "app":
    cursor.execute(
        "SELECT loader, duration FROM orders WHERE id = ?", (order_id,)
    )
    order = cursor.fetchone()
    if not order:
      conn.close()
      bot.answer_callback_query(call.id, "Order not found!", show_alert=True)
      return

    loader_code, duration = order[0], order[1]
    loader_display = get_loader_display_name(loader_code)

    cursor.execute(
        "SELECT id, license_key FROM keys_table WHERE duration = ? AND status = 'unused' LIMIT 1",
        (duration,),
    )
    key_row = cursor.fetchone()

    if key_row:
      key_id = key_row[0]
      license_key = key_row[1]

      cursor.execute(
          "UPDATE keys_table SET status = 'used', assigned_to = ? WHERE id ="
          " ?",
          (user_id, key_id),
      )
      cursor.execute(
          "UPDATE orders SET status = 'approved' WHERE id = ?", (order_id,)
      )
      conn.commit()
      conn.close()

      bot.send_message(
          user_id,
          f"🎉 *Payment Verified Successfully!*\n\n• *Loader:* {loader_display}"
          f" ({duration})\n• *Your License Key:*\n`{license_key}`",
          parse_mode="Markdown",
      )
      bot.edit_message_text(
          "✅ *Approved & Key Sent Successfully!*",
          call.message.chat.id,
          call.message.message_id,
          parse_mode="Markdown",
      )
    else:
      conn.close()
      bot.answer_callback_query(
          call.id,
          f"❌ Out of stock keys for duration ({duration})!",
          show_alert=True,
      )

  elif action == "rej":
    cursor.execute(
        "UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,)
    )
    conn.commit()
    conn.close()
    bot.send_message(
        user_id, "❌ Payment verification rejected. Contact support."
    )
    bot.edit_message_text(
        "❌ *Payment Rejected!*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )

  elif action == "resapp":
    cursor.execute(
        "INSERT OR IGNORE INTO resellers (user_id) VALUES (?)", (user_id,)
    )
    cursor.execute(
        "UPDATE reseller_orders SET status = 'approved' WHERE id = ?",
        (order_id,),
    )
    conn.commit()
    conn.close()

    bot.send_message(
        user_id,
        "🎉 *Congratulations!*\nYour Reseller Ship has been approved by admin."
        " Now you have reseller/admin access in the bot for 1 Month!",
        parse_mode="Markdown",
    )
    bot.edit_message_text(
        "⭐ *Reseller Approved Successfully!*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )

  elif action == "resrej":
    cursor.execute(
        "UPDATE reseller_orders SET status = 'rejected' WHERE id = ?",
        (order_id,),
    )
    conn.commit()
    conn.close()
    bot.send_message(
        user_id, "❌ Reseller payment verification was rejected."
    )
    bot.edit_message_text(
        "❌ *Reseller Request Rejected!*",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )


# --- RESET KEY HANDLER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("reset_"))
def handle_reset_key(call):
  key_id = call.data.split("_")[1]
  user_id = call.from_user.id

  bot.answer_callback_query(
      call.id,
      "🔄 Reset request sent to owner/admin successfully!",
      show_alert=True,
  )
  bot.send_message(
      ADMIN_ID,
      f"⚠️ *Key Reset Request*\nUser ID: `{user_id}` requested reset for Key ID:"
      f" `{key_id}`",
      parse_mode="Markdown",
  )


# --- ADMIN COMMAND: ADD SINGLE KEY (/addkey) ---
@bot.message_handler(commands=["addkey"])
def add_key(message):
  user_id = message.from_user.id
  if not is_admin_or_reseller(user_id):
    bot.reply_to(message, "❌ You are not authorized to use this command!")
    return

  try:
    parts = message.text.split(" ", 3)
    loader_code = parts[1]
    duration = parts[2]
    key = parts[3].strip()
    loader_display = get_loader_display_name(loader_code)

    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO keys_table (loader, duration, license_key, status) VALUES"
        " (?, ?, ?, 'unused')",
        (loader_code, duration, key),
    )
    conn.commit()
    conn.close()

    bot.reply_to(
        message,
        f"✅ Key added successfully!\n• *Loader:* {loader_display}\n• *Duration:"
        f"* {duration}\n• *Key:* `{key}`",
        parse_mode="Markdown",
    )
  except Exception as e:
    bot.reply_to(
        message,
        "❌ Format error!\nUse format: `/addkey [Loader] [Duration] [Key]`\nExample:"
        " `/addkey NEXA 5 Hour NICE-KEY-123`",
        parse_mode="Markdown",
    )


# --- ADMIN COMMAND: SMART MULTI-DURATION BULK ADD (/bulkall) ---
@bot.message_handler(commands=["bulkall"])
def bulk_all_start(message):
  user_id = message.from_user.id
  if not is_admin_or_reseller(user_id):
    bot.reply_to(message, "❌ You are not authorized to use this command!")
    return

  try:
    parts = message.text.split(" ", 1)
    loader_code = parts[1].strip()

    user_states[user_id] = {"type": "bulk_all", "loader": loader_code}
    bot.reply_to(
        message,
        f"📦 *Smart Multi-Duration Bulk Add Activated*\n*Loader:* {loader_code}\n\n"
        "Ab apne keys is format mein **ek line mein ek key** bhej dein:\n"
        "`KEY | DURATION`\n\n"
        "*Example (Mixed Durations):*\n"
        "`KEY123ABC | 1 Day`\n"
        "`KEY456DEF | 2 Day`\n"
        "`KEY789GHI | 3 Day`\n"
        "`KEY999XYZ | 30 Day`",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_bulk_all_keys)
  except Exception as e:
    bot.reply_to(
        message,
        "❌ Format error!\nUse format: `/bulkall [Loader]`\nExample:"
        " `/bulkall NEXA`",
        parse_mode="Markdown",
    )


def process_bulk_all_keys(message):
  user_id = message.from_user.id
  if user_id not in user_states or user_states[user_id]["type"] != "bulk_all":
    return

  state = user_states[user_id]
  loader_code = state["loader"]
  del user_states[user_id]

  raw_text = message.text
  lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

  if not lines:
    bot.reply_to(message, "❌ Koi data nahi mila! Operation cancelled.")
    return

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  success_count = 0
  failed_lines = 0

  for line in lines:
    if "|" in line:
      parts = line.split("|", 1)
      key = parts[0].strip()
      duration = parts[1].strip()
      if key and duration:
        cursor.execute(
            "INSERT INTO keys_table (loader, duration, license_key, status)"
            " VALUES (?, ?, ?, 'unused')",
            (loader_code, duration, key),
        )
        success_count += 1
      else:
        failed_lines += 1
    else:
      failed_lines += 1

  conn.commit()
  conn.close()

  loader_display = get_loader_display_name(loader_code)
  bot.reply_to(
      message,
      f"✅ *Bulk Add Completed!* 🎉\n• *Loader:* {loader_display}\n•"
      f" *Successfully Added:* {success_count} keys\n• *Failed/Invalid"
      f" Lines:* {failed_lines}",
      parse_mode="Markdown",
  )


# --- CLEAR WEBHOOK TO PREVENT 409 CONFLICT ERROR ---
try:
  bot.remove_webhook()
  bot.delete_webhook(drop_pending_updates=True)
except Exception:
  pass

print("Bot is running with full features...")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
