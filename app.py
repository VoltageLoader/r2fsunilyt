import os
import threading
import time
from flask import Flask, jsonify, request
import telebot
from telebot import types

# Aapka Bot Token
TOKEN = "8052389503:AAEkPCKUqOHgbp8FIhB2Z3LtB9u0GvMLnvk"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Payment requests data store karne ke liye dictionary
PAYMENT_REQUESTS = {}


@app.route("/api/submit_payment", methods=["POST"])
def submit_payment():
  try:
    data = request.json
    utr = data.get("utr")
    plan = data.get("plan")
    amount = data.get("amount")
    admin_id = data.get("admin_id")

    # Request ko pending status me save karein
    PAYMENT_REQUESTS[utr] = {"status": "pending", "plan": plan}

    # Admin ko Telegram par buttons ke sath message bhejein
    markup = types.InlineKeyboardMarkup()
    btn_verify = types.InlineKeyboardButton(
        "✅ Verify & Send Key", callback_data=f"verify_{utr}"
    )
    btn_reject = types.InlineKeyboardButton(
        "❌ Reject", callback_data=f"reject_{utr}"
    )
    markup.add(btn_verify, btn_reject)

    message_text = (
        f"🚨 *NEW SUBSCRIPTION PAYMENT RECEIVED!*\n\n"
        f"📦 *Plan:* {plan}\n"
        f"💵 *Amount:* ₹{amount}\n"
        f"🔢 *UTR ID:* `{utr}`\n\n"
        f"Kripya verify ya reject karein."
    )
    bot.send_message(
        admin_id, message_text, parse_mode="Markdown", reply_markup=markup
    )
    return jsonify({"status": "success"})
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)})


@app.route("/api/check_status/<utr>", methods=["GET"])
def check_status(utr):
  if utr in PAYMENT_REQUESTS:
    return jsonify(PAYMENT_REQUESTS[utr])
  return jsonify({"status": "not_found"})


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("verify_")
    or call.data.startswith("reject_")
)
def handle_admin_action(call):
  action, utr = call.data.split("_", 1)

  if utr not in PAYMENT_REQUESTS:
    bot.answer_callback_query(call.id, "Request expire ho chuki hai!")
    return

  plan = PAYMENT_REQUESTS[utr]["plan"]

  if action == "verify":
    # Plan ke hisab se automatic key generate karein
    generated_key = f"NEXA-{plan.upper().replace(' ', '')}-{int(time.time())}"

    # Status approved aur key update karein
    PAYMENT_REQUESTS[utr] = {
        "status": "approved",
        "key": generated_key,
        "plan": plan,
    }

    bot.edit_message_text(
        f"✅ *Payment Verified & Key Sent to App!*\n\n"
        f"📦 Plan: {plan}\n"
        f"🔢 UTR: `{utr}`\n"
        f"🔑 Generated Key: `{generated_key}`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id, "Verified Successfully!")

  elif action == "reject":
    # Status rejected update karein
    PAYMENT_REQUESTS[utr] = {"status": "rejected", "plan": plan}

    bot.edit_message_text(
        f"❌ *Payment Rejected!*\n\n"
        f"📦 Plan: {plan}\n"
        f"🔢 UTR: `{utr}`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id, "Payment Rejected!")


def run_flask():
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


if __name__ == "__main__":
  threading.Thread(target=run_flask).start()
  print("🤖 Bot and API Server successfully start ho gaye hain...")
  bot.infinity_polling()
