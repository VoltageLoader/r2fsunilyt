import sqlite3
import urllib.parse
import telebot
from telebot import types

# --- CONFIGURATION ---
TOKEN = "8052389503:AAG8O3ZH4NCJJrW7erp4u9W3IfKm4z18itk"  # Apna Telegram Bot Token
ADMIN_ID = 6795305850  # Apni Telegram Numeric Chat ID
UPI_ID = "8905094188@ybl"  # Aapka UPI ID
UPI_NAME = "Nexa Cyber"  # App ya Store ka Naam
OWNER_USERNAME = "R2FSUNILYT"  # Owner ka Telegram username
SETUP_CHANNEL_URL = "https://t.me/VoltageLoader"  # Setup channel link

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
                        status TEXT DEFAULT 'pending')""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS reseller_orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        utr TEXT,
                        amount INTEGER,
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


# --- REPLY KEYBOARD (MENU BUTTONS NEAR CHAT BAR) ---
def get_main_reply_keyboard():
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  btn1 = types.KeyboardButton("🛒 PURCHASE KEY")
  btn2 = types.KeyboardButton("🔐 MY KEYS")
  btn3 = types.KeyboardButton("🤝 BUY RESELLERSHIP")
  btn4 = types.KeyboardButton("♻️ SETUP CHANNEL")
  btn5 = types.KeyboardButton("💬 CONTACT SUPPORT")
  markup.add(btn1, btn2)
  markup.add(btn3)
  markup.add(btn4, btn5)
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
  # Clear state on start
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
  # Clear pending UTR step if user clicks a menu button
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
    user_states[message.from_user.id] = {
        "type": "reseller",
        "amount": amount,
    }
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

    caption_text = (
        "💳 *SCAN & PAY (AUTO AMOUNT)*\n\n"
        "• *LOADER:* Reseller Ship (1 Month)\n"
        "• *PLAN:* 30 Days\n"
        f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
        f"• *UPI ID:* `{UPI_ID}`\n\n"
        "⚠️ *PAYMENT INSTRUCTIONS*\n\n"
        "1️⃣ *QR SCAN KAREIN — AMOUNT AUTOMATICALLY AA JAYEGA.*\n"
        "2️⃣ *PAYMENT KE BAAD 12-DIGIT UTR / TRANSACTION ID YAHIN CHAT MEIN"
        " BHEJEIN.*\n"
        "✅ *PAYMENT VERIFY HO JAYEGA.*"
    )
    bot.send_photo(
        chat_id=message.chat.id,
        photo=qr_api_url,
        caption=caption_text,
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_utr)

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


# --- SELECT PLANS FOR CHOSEN LOADER ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("loader_"))
def select_plan(call):
  loader_code = call.data.split("_")[1]
  loader_display = get_loader_display_name(loader_code)
  markup = types.InlineKeyboardMarkup(row_width=2)

  plans = [
      ("⏱️ 5 Hour - ₹30", "5 Hour", 30),
      ("⏱️ 1 Day - ₹60", "1 Day", 60),
      ("⏱️ 2 Day - ₹100", "2 Day", 100),
      ("⏱️ 3 Day - ₹180", "3 Day", 180),
      ("⏱ 7 Day - ₹399", "7 Day", 399),
      ("⏱️ 30 Day - ₹699", "30 Day", 699),
  ]

  for title, duration, amount in plans:
    markup.add(
        types.InlineKeyboardButton(
            title, callback_data=f"plan_{loader_code}_{duration}_{amount}"
        )
    )

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

  user_states[call.from_user.id] = {
      "type": "plan",
      "loader": loader_code,
      "duration": duration,
      "amount": amount,
  }

  upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}.00&cu=INR"
  qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_url)}"

  caption_text = (
      "💳 *SCAN & PAY (AUTO AMOUNT)*\n\n"
      f"• *LOADER:* {loader_display}\n"
      f"• *PLAN:* {duration}\n"
      f"• *AMOUNT:* ₹{amount} (AUTO-FILLED)\n"
      f"• *UPI ID:* `{UPI_ID}`\n\n"
      "⚠️ *PAYMENT INSTRUCTIONS*\n\n"
      "1️⃣ *QR SCAN KAREIN — AMOUNT AUTOMATICALLY AA JAYEGA.*\n"
      "2️⃣ *PAYMENT KE BAAD 12-DIGIT UTR / TRANSACTION ID YAHIN CHAT MEIN"
      " BHEJEIN.*\n"
      "✅ *PAYMENT VERIFY HO JAYEGA.*"
  )

  bot.send_photo(
      chat_id=call.message.chat.id,
      photo=qr_api_url,
      caption=caption_text,
      parse_mode="Markdown",
  )
  bot.register_next_step_handler(call.message, process_utr)


# --- UTR PROCESS & ADMIN NOTIFICATION ---
def process_utr(message):
  user_id = message.from_user.id

  # If user sent a menu button or command during UTR input step, ignore UTR and let menu handler deal with it
  if message.text in [
      "🛒 PURCHASE KEY",
      "🔐 MY KEYS",
      "🤝 BUY RESELLERSHIP",
      "♻️ SETUP CHANNEL",
      "💬 CONTACT SUPPORT",
  ] or message.text.startswith("/"):
    if user_id in user_states:
      del user_states[user_id]
    handle_reply_menu(message)
    return

  if user_id not in user_states:
    bot.send_message(
        user_id,
        "❌ Session expired or invalid action. Please click /start to"
        " restart.",
    )
    return

  utr = message.text.strip()

  # Strict UTR check (must be at least 8 chars and not random gibberish/menu text)
  if len(utr) < 8 or len(utr) > 25:
    bot.send_message(
        user_id,
        "❌ Invalid UTR/Transaction ID! Please send a valid 12-digit UTR"
        " number:",
    )
    bot.register_next_step_handler(message, process_utr)
    return

  state = user_states[user_id]
  action_type = state["type"]

  # Clear state immediately so double texts don't re-trigger
  del user_states[user_id]

  conn = sqlite3.connect("bot_database.db", check_same_thread=False)
  cursor = conn.cursor()

  if action_type == "plan":
    loader_code = state["loader"]
    duration = state["duration"]
    amount = state["amount"]
    loader_display = get_loader_display_name(loader_code)

    cursor.execute(
        "INSERT INTO orders (user_id, utr, loader, duration, amount, status)"
        " VALUES (?, ?, ?, ?, ?, 'pending')",
        (user_id, utr, loader_code, duration, amount),
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    bot.send_message(
        user_id, "⏳ UTR received! Verifying payment with admin. Please wait..."
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
        f"🔔 *New Plan Payment Request!*\n\n👤 *User ID:* `{user_id}`\n📦"
        f" *Loader:* {loader_display} ({duration})\n💵 *Amount:*"
        f" ₹{amount}\n💳 *UTR Number:* `{utr}`"
    )
    bot.send_message(
        ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup
    )

  elif action_type == "reseller":
    amount = state["amount"]
    cursor.execute(
        "INSERT INTO reseller_orders (user_id, utr, amount, status) VALUES (?,"
        " ?, ?, 'pending')",
        (user_id, utr, amount),
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    bot.send_message(
        user_id,
        "⏳ Reseller UTR received! Admin verification in progress. Please"
        " wait...",
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
        f"⭐ *New Reseller Request!*\n\n👤 *User ID:* `{user_id}`\n💵 *Amount:*"
        f" ₹{amount}\n💳 *UTR Number:* `{utr}`"
    )
    bot.send_message(
        ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup
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
        "SELECT id, license_key FROM keys_table WHERE loader = ? AND duration ="
        " ? AND status = 'unused' LIMIT 1",
        (loader_code, duration),
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
          f"❌ Out of stock keys for {loader_display} ({duration})!",
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


# --- ADMIN / RESELLER COMMAND: ADD KEYS (/addkey) ---
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


# --- CLEAR WEBHOOK TO PREVENT 409 CONFLICT ERROR ---
try:
  bot.remove_webhook()
  bot.delete_webhook(drop_pending_updates=True)
except Exception:
  pass

print("Bot is running with full features...")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
  
