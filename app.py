import os
import json
import time
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = "8052389503:AAEkPCKUqOHgbp8FIhB2Z3LtB9u0GvMLnvk"
ADMIN_ID = 6795305850

DB_FILE = "database.json"

# --- Database Load & Save Functions (Persistence) ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "stocks": {
            "5hr": [],
            "1 Day": [],
            "7 Days": [],
            "30 Days": []
        },
        "used_keys": [],
        "payments": {}
    }

def save_db(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Database save error:", e)

db = load_db()

# --- 1. Free Key Endpoint (5 Hr Key) ---
@app.route('/api/submit_free_task', methods=['POST'])
def submit_free_task():
    global db
    db = load_db()
    stock_5hr = db["stocks"].get("5hr", [])
    
    if stock_5hr:
        assigned_key = stock_5hr.pop(0)
        db["used_keys"].append({"key": assigned_key, "category": "5hr", "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        save_db(db)
        return jsonify({"status": "success", "key": assigned_key})
    else:
        return jsonify({"status": "error", "message": "❌ 5-Hour stock khatam ho gaya hai! Admin se contact karein."}), 400

# --- 2. Payment Submission Endpoint ---
@app.route('/api/submit_payment', methods=['POST'])
def submit_payment():
    global db
    db = load_db()
    data = request.json or {}
    utr = data.get("utr")
    plan = data.get("plan") # e.g. "1 Day", "7 Days", "30 Days"
    amount = data.get("amount")

    if not utr or not plan:
        return jsonify({"error": "Invalid data"}), 400

    db["payments"][utr] = {"status": "pending", "plan": plan, "key": ""}
    save_db(db)

    # Send Telegram Notification to Admin with Inline Buttons
    msg = (
        f"🚨 *NEW PAYMENT RECEIVED!*\n\n"
        f"📦 *Plan:* {plan}\n"
        f"💰 *Amount:* ₹{amount}\n"
        f"💳 *UTR ID:* `{utr}`\n\n"
        f"Niche diye gaye button par click karke verify karein:"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Send Key", "callback_data": f"approve_{utr}_{plan}"},
                {"text": "❌ Reject", "callback_data": f"reject_{utr}"}
            ]
        ]
    }

    send_telegram_message(ADMIN_ID, msg, keyboard)
    return jsonify({"status": "submitted"})

# --- 3. Check Status Endpoint (Polled by App) ---
@app.route('/api/check_status/<utr>', methods=['GET'])
def check_status(utr):
    global db
    db = load_db()
    payment_info = db["payments"].get(utr)
    if not payment_info:
        return jsonify({"status": "pending"})
    
    return jsonify({
        "status": payment_info["status"],
        "key": payment_info.get("key", "")
    })

# --- Helper Functions for Telegram Bot ---
def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram send error:", e)

def answer_callback_query(callback_query_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
    except Exception:
        pass

# --- Telegram Bot Long Polling Thread (Admin Menu & Actions) ---
def telegram_polling():
    offset = 0
    print("🤖 Telegram Bot Polling Started with Stock Management...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            data = response.json()

            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # Handle Text Commands & Menu
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["from"]["id"]
                        text = msg.get("text", "")

                        if chat_id != ADMIN_ID:
                            continue

                        global db
                        db = load_db()

                        if text in ["/start", "/menu"]:
                            menu_text = "🛠 *ADMIN CONTROL PANEL*\n\nNiche diye gaye options select karein:"
                            keyboard = {
                                "inline_keyboard": [
                                    [{"text": "📊 Check Stock", "callback_data": "menu_stock"}],
                                    [
                                        {"text": "➕ Add 5hr", "callback_data": "add_prompt_5hr"},
                                        {"text": "➕ Add 1 Day", "callback_data": "add_prompt_1 Day"}
                                    ],
                                    [
                                        {"text": "➕ Add 7 Days", "callback_data": "add_prompt_7 Days"},
                                        {"text": "➕ Add 30 Days", "callback_data": "add_prompt_30 Days"}
                                    ],
                                    [{"text": "📜 View Used Keys", "callback_data": "menu_used"}]
                                ]
                            }
                            send_telegram_message(chat_id, menu_text, keyboard)

                        elif text.startswith("/add "):
                            # Format: /add 1 Day KEY123 or /add 5hr KEYABC
                            parts = text.split(" ", 2)
                            if len(parts) >= 3:
                                cat = parts[1]
                                key_val = parts[2].strip()
                                # Normalize category name if needed
                                if cat in ["5hr", "1", "7", "30"]:
                                    if cat == "1": cat = "1 Day"
                                    elif cat == "7": cat = "7 Days"
                                    elif cat == "30": cat = "30 Days"
                                
                                if cat in db["stocks"]:
                                    db["stocks"][cat].append(key_val)
                                    save_db(db)
                                    send_telegram_message(chat_id, f"✅ Key added successfully to *{cat}* stock!\nTotal keys: {len(db['stocks'][cat])}")
                                else:
                                    send_telegram_message(chat_id, "❌ Invalid category! Use: 5hr, 1 Day, 7 Days, 30 Days")
                            else:
                                send_telegram_message(chat_id, "⚠️ Format galat hai. Use karein:\n`/add 1 Day YOUR_KEY`")

                    # Handle Button Clicks (Callback Queries)
                    elif "callback_query" in update:
                        cq = update["callback_query"]
                        cq_id = cq["id"]
                        data_str = cq["data"]
                        user_id = cq["from"]["id"]

                        if user_id != ADMIN_ID:
                            answer_callback_query(cq_id, "⚠ You are not authorized!")
                            continue

                        db = load_db()

                        if data_str == "menu_stock":
                            stock_msg = (
                                f"📊 *CURRENT STOCK STATUS:*\n\n"
                                f"🕒 *5 Hr Keys:* {len(db['stocks']['5hr'])} available\n"
                                f"⚡ *1 Day Keys:* {len(db['stocks']['1 Day'])} available\n"
                                f"🔥 *7 Days Keys:* {len(db['stocks']['7 Days'])} available\n"
                                f"👑 *30 Days Keys:* {len(db['stocks']['30 Days'])} available\n"
                                f"🗑 *Used/Sold Keys:* {len(db['used_keys'])} total"
                            )
                            answer_callback_query(cq_id, "Stock fetched!")
                            send_telegram_message(ADMIN_ID, stock_msg)

                        elif data_str == "menu_used":
                            used_list = db["used_keys"][-15:] # Last 15 used keys
                            if used_list:
                                used_text = "📜 *RECENT USED / SOLD KEYS:*\n\n"
                                for item in used_list:
                                    used_text += f"• `{item['key']}` ({item['category']}) - {item['time']}\n"
                            else:
                                used_text = "📜 Koi bhi key abhi tak used nahi hui hai."
                            answer_callback_query(cq_id, "Used keys fetched!")
                            send_telegram_message(ADMIN_ID, used_text)

                        elif data_str.startswith("add_prompt_"):
                            cat_name = data_str.replace("add_prompt_", "")
                            prompt_msg = f"➕ *Add Key for {cat_name}*\n\nIs format me message bhejein:\n`/add {cat_name} YOUR_NEW_KEY_HERE`"
                            answer_callback_query(cq_id, f"Add {cat_name}")
                            send_telegram_message(ADMIN_ID, prompt_msg)

                        elif data_str.startswith("approve_"):
                            parts = data_str.split("_")
                            utr = parts[1]
                            plan = "_".join(parts[2:]) # e.g. "1 Day"
                            
                            stock_list = db["stocks"].get(plan, [])
                            if stock_list:
                                assigned_key = stock_list.pop(0)
                                db["used_keys"].append({"key": assigned_key, "category": plan, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
                                
                                if utr in db["payments"]:
                                    db["payments"][utr]["status"] = "approved"
                                    db["payments"][utr]["key"] = assigned_key
                                
                                save_db(db)
                                answer_callback_query(cq_id, f"Approved! Key: {assigned_key}")
                                send_telegram_message(ADMIN_ID, f"✅ Payment Approved for UTR: `{utr}`\n🔑 Assigned Key: `{assigned_key}`\n📦 Stock left in {plan}: {len(stock_list)}")
                            else:
                                answer_callback_query(cq_id, f"❌ Stock empty for {plan}!")
                                send_telegram_message(ADMIN_ID, f"⚠️ Stock khatam ho gaya hai '{plan}' ke liye! Pehle key add karein.")

                        elif data_str.startswith("reject_"):
                            utr = parts = data_str.split("_")[1]
                            if utr in db["payments"]:
                                db["payments"][utr]["status"] = "rejected"
                                save_db(db)
                            
                            answer_callback_query(cq_id, "Payment Rejected.")
                            send_telegram_message(ADMIN_ID, f"❌ Payment Rejected for UTR: `{utr}`")

        except Exception as e:
            print("Polling error:", e)
            time.sleep(5)
        time.sleep(1)

# Start background polling thread
threading.Thread(target=telegram_polling, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
