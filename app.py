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
admin_state = {}  # Admin ke multi-step actions ke liye (e.g. bulk add, delete)

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
        assigned_key = stock_5hr.pop(0).strip()
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
        "key": payment_info.get("key", "").strip()
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

# --- Telegram Bot Long Polling Thread (Admin Menu & Advanced Controls) ---
def telegram_polling():
    offset = 0
    print("🤖 Telegram Bot Polling Started with Super Admin Panel & Key Generation...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            data = response.json()

            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["from"]["id"]
                        text = msg.get("text", "")

                        if chat_id != ADMIN_ID:
                            continue

                        global db
                        db = load_db()

                        # Check if admin is in a state (e.g., waiting for bulk keys input)
                        if ADMIN_ID in admin_state:
                            state_info = admin_state[ADMIN_ID]
                            action = state_info.get("action")
                            cat = state_info.get("category")

                            if action == "bulk_add":
                                lines = [line.strip() for line in text.split("\n") if line.strip()]
                                added_count = 0
                                for key_val in lines:
                                    if cat in db["stocks"]:
                                        db["stocks"][cat].append(key_val)
                                        added_count += 1
                                save_db(db)
                                del admin_state[ADMIN_ID]
                                send_telegram_message(chat_id, f"✅ Successfully added `{added_count}` keys to *{cat}* stock!\nTotal keys now: {len(db['stocks'][cat])}")
                                continue

                        if text in ["/start", "/menu"]:
                            if ADMIN_ID in admin_state:
                                del admin_state[ADMIN_ID]
                            menu_text = "👑 *SUPER ADMIN CONTROL PANEL*\n\nNiche diye gaye options select karein:"
                            keyboard = {
                                "inline_keyboard": [
                                    [
                                        {"text": "📊 Check Stock", "callback_data": "menu_stock"},
                                        {"text": "🔑 Generate Key", "callback_data": "menu_gen_key"}
                                    ],
                                    [
                                        {"text": "➕ Add Single", "callback_data": "menu_add_single"},
                                        {"text": "📦 Add Bulk", "callback_data": "menu_add_bulk"}
                                    ],
                                    [
                                        {"text": "🗑️ Delete Stock", "callback_data": "menu_del_stock"},
                                        {"text": "📜 View Sold Keys", "callback_data": "menu_used"}
                                    ]
                                ]
                            }
                            send_telegram_message(chat_id, menu_text, keyboard)

                        elif text.startswith("/add "):
                            parts = text.split()
                            if len(parts) >= 3:
                                raw_cat = parts[1].lower()
                                cat = None
                                key_start_idx = 2
                                
                                if raw_cat == "5hr":
                                    cat = "5hr"
                                elif raw_cat in ["1day", "1"]:
                                    cat = "1 Day"
                                    key_start_idx = 3 if len(parts) > 3 and parts[2].lower() in ["day", "days"] else 2
                                elif raw_cat in ["7day", "7days", "7"]:
                                    cat = "7 Days"
                                    key_start_idx = 3 if len(parts) > 3 and parts[2].lower() in ["day", "days"] else 2
                                elif raw_cat in ["30day", "30days", "30"]:
                                    cat = "30 Days"
                                    key_start_idx = 3 if len(parts) > 3 and parts[2].lower() in ["day", "days"] else 2
                                else:
                                    cat = parts[1]

                                key_val = " ".join(parts[key_start_idx:]).strip()
                                
                                if cat in db["stocks"] and key_val:
                                    db["stocks"][cat].append(key_val)
                                    save_db(db)
                                    send_telegram_message(chat_id, f"✅ Key added to *{cat}*!\n🔑 `{key_val}`\nTotal: {len(db['stocks'][cat])}")
                                else:
                                    send_telegram_message(chat_id, "❌ Invalid category or empty key!")
                            else:
                                send_telegram_message(chat_id, "⚠ Format: `/add 1day YOUR_KEY`")

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
                                f"🕒 *5 Hr Keys:* {len(db['stocks']['5hr'])}\n"
                                f"⚡ *1 Day Keys:* {len(db['stocks']['1 Day'])}\n"
                                f"🔥 *7 Days Keys:* {len(db['stocks']['7 Days'])}\n"
                                f"👑 *30 Days Keys:* {len(db['stocks']['30 Days'])}\n"
                                f"🗑 *Total Sold Keys:* {len(db['used_keys'])}"
                            )
                            answer_callback_query(cq_id, "Stock fetched!")
                            send_telegram_message(ADMIN_ID, stock_msg)

                        # --- NEW: Generate Key Menu & Logic ---
                        elif data_str == "menu_gen_key":
                            answer_callback_query(cq_id, "Generate Key Menu")
                            markup = {
                                "inline_keyboard": [
                                    [
                                        {"text": "⏱ 5hr", "callback_data": "gen_cat_5hr"},
                                        {"text": "⚡ 1 Day", "callback_data": "gen_cat_1 Day"}
                                    ],
                                    [
                                        {"text": "🔥 7 Days", "callback_data": "gen_cat_7 Days"},
                                        {"text": "👑 30 Days", "callback_data": "gen_cat_30 Days"}
                                    ]
                                ]
                            }
                            send_telegram_message(ADMIN_ID, "🔑 *GENERATE KEY*\n\nDuration select karein:", markup)

                        elif data_str.startswith("gen_cat_"):
                            cat_name = data_str.replace("gen_cat_", "")
                            stock_list = db["stocks"].get(cat_name, [])
                            if stock_list:
                                assigned_key = stock_list.pop(0).strip()
                                db["used_keys"].append({
                                    "key": assigned_key,
                                    "category": cat_name,
                                    "time": time.strftime("%Y-%m-%d %H:%M:%S")
                                })
                                save_db(db)
                                answer_callback_query(cq_id, "Key Generated!")
                                send_telegram_message(
                                    ADMIN_ID,
                                    f"✅ *KEY GENERATED SUCCESSFULLY!*\n\n"
                                    f"• *Duration:* {cat_name}\n"
                                    f"• *Key:* `{assigned_key}`\n"
                                    f"• *Stock Left:* {len(stock_list)}"
                                )
                            else:
                                answer_callback_query(cq_id, "❌ Out of stock!")
                                send_telegram_message(
                                    ADMIN_ID,
                                    f"❌ *Out of Stock!*\nDuration *{cat_name}* ke liye koi unused key available nahi hai."
                                )
                        # ----------------------------------------

                        elif data_str == "menu_used":
                            used_list = db["used_keys"][-15:]
                            if used_list:
                                used_text = "📜 *RECENT SOLD KEYS (Last 15):*\n\n"
                                for item in used_list:
                                    used_text += f"• `{item['key']}` ({item['category']}) - {item['time']}\n"
                            else:
                                used_text = "📜 Koi bhi key abhi tak used nahi hui hai."
                            answer_callback_query(cq_id, "Sold keys fetched!")
                            send_telegram_message(ADMIN_ID, used_text)

                        elif data_str == "menu_add_single":
                            answer_callback_query(cq_id, "Add Single Key")
                            send_telegram_message(ADMIN_ID, "➕ *Add Single Key*\n\nFormat use karein:\n`/add 1day YOUR_KEY`\n(Categories: `5hr`, `1 Day`, `7 Days`, `30 Days`)")

                        elif data_str == "menu_add_bulk":
                            answer_callback_query(cq_id, "Add Bulk Keys")
                            markup = {
                                "inline_keyboard": [
                                    [
                                        {"text": "⏱ 5hr", "callback_data": "bulk_cat_5hr"},
                                        {"text": "⚡ 1 Day", "callback_data": "bulk_cat_1 Day"}
                                    ],
                                    [
                                        {"text": "🔥 7 Days", "callback_data": "bulk_cat_7 Days"},
                                        {"text": "👑 30 Days", "callback_data": "bulk_cat_30 Days"}
                                    ]
                                ]
                            }
                            send_telegram_message(ADMIN_ID, "📦 *BULK ADD STOCK*\n\nKis category mein keys add karni hain select karein:", markup)

                        elif data_str.startswith("bulk_cat_"):
                            cat_name = data_str.replace("bulk_cat_", "")
                            admin_state[ADMIN_ID] = {"action": "bulk_add", "category": cat_name}
                            answer_callback_query(cq_id, f"Selected {cat_name}")
                            send_telegram_message(ADMIN_ID, f"📦 *Bulk Add: {cat_name}*\n\nAb multiple keys **ek line mein ek key** karke yahin chat mein paste/send karein:")

                        elif data_str == "menu_del_stock":
                            answer_callback_query(cq_id, "Delete Stock Menu")
                            markup = {
                                "inline_keyboard": [
                                    [
                                        {"text": "🗑️ Clear 5hr Stock", "callback_data": "clear_stock_5hr"},
                                        {"text": "🗑️ Clear 1 Day Stock", "callback_data": "clear_stock_1 Day"}
                                    ],
                                    [
                                        {"text": "🗑️ Clear 7 Days Stock", "callback_data": "clear_stock_7 Days"},
                                        {"text": "🗑️ Clear 30 Days Stock", "callback_data": "clear_stock_30 Days"}
                                    ]
                                ]
                            }
                            send_telegram_message(ADMIN_ID, "🗑 *DELETE STOCK MENU*\n\nCategory select karein jiska saara unused stock clear karna hai:", markup)

                        elif data_str.startswith("clear_stock_"):
                            cat_name = data_str.replace("clear_stock_", "")
                            if cat_name in db["stocks"]:
                                count = len(db["stocks"][cat_name])
                                db["stocks"][cat_name] = []
                                save_db(db)
                                answer_callback_query(cq_id, f"Cleared {count} keys!")
                                send_telegram_message(ADMIN_ID, f"✅ Category *{cat_name}* ka saara unused stock ({count} keys) delete kar diya gaya hai.")

                        elif data_str.startswith("approve_"):
                            parts = data_str.split("_")
                            utr = parts[1]
                            plan = "_".join(parts[2:])
                            
                            stock_list = db["stocks"].get(plan, [])
                            if stock_list:
                                assigned_key = stock_list.pop(0).strip()
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
                            utr = data_str.split("_")[1]
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
