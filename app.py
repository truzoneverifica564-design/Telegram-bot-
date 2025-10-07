import json
import time
import threading
import requests
from collections import deque
from flask import Flask, request, jsonify
import random

# Load settings from config.json
with open("config.json", "r") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = config["TELEGRAM_CHAT_ID"]
FOREX_API_KEY = config["FOREX_API_KEY"]
FOREX_API_URL = config["FOREX_API_URL"]
POLL_INTERVAL = config["POLL_INTERVAL"]
SHORT_WINDOW = config["SHORT_WINDOW"]
LONG_WINDOW = config["LONG_WINDOW"]
SYMBOL = config["SYMBOL"]

# Your Render app URL (replace with your real one)
WEBHOOK_URL = "https://telegram-bot-30bi.onrender.com/webhook"

app = Flask(__name__)

price_history = deque(maxlen=LONG_WINDOW + 2)
last_signal = {"side": None, "price": None}


def send_telegram(text: str, chat_id: str = None):
    """Send a message to Telegram chat."""
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print("Telegram send error:", e)
        return False


def fetch_price():
    """Get latest EUR/USD price."""
    try:
        if FOREX_API_URL:
            r = requests.get(FOREX_API_URL, params={"apikey": FOREX_API_KEY}, timeout=10)
            data = r.json()
            return float(data.get("price") or data.get("rate") or data.get("last") or data.get("close"))
        else:
            r = requests.get("https://api.exchangerate.host/latest?base=EUR&symbols=USD", timeout=10)
            return float(r.json()["rates"]["USD"])
    except Exception as e:
        print("Fetch price error:", e)
        return None


def compute_sma(prices, window):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def generate_signal():
    """Simple moving-average crossover strategy."""
    if len(price_history) < LONG_WINDOW:
        return None, None
    short_sma = compute_sma(list(price_history), SHORT_WINDOW)
    long_sma = compute_sma(list(price_history), LONG_WINDOW)
    current_price = price_history[-1]

    if short_sma > long_sma and last_signal["side"] != "BUY":
        return "BUY", current_price
    elif short_sma < long_sma and last_signal["side"] != "SELL":
        return "SELL", current_price
    else:
        return None, None


def polling_loop():
    """Background price monitoring loop."""
    print("📡 Polling started...")
    while True:
        price = fetch_price()
        if price:
            price_history.append(price)
            print(f"EUR/USD = {price}")
            side, p = generate_signal()
            if side:
                tp = round(p + 0.0030, 5) if side == "BUY" else round(p - 0.0030, 5)
                sl = round(p - 0.0020, 5) if side == "BUY" else round(p + 0.0020, 5)
                msg = f"💹 <b>{side}</b> {SYMBOL} @ {p}\n🎯 TP: {tp} | 🛑 SL: {sl}"
                send_telegram(msg)
                last_signal.update({"side": side, "price": p})
        else:
            print("Failed to fetch price.")
        time.sleep(POLL_INTERVAL)


def simple_ai_response(text: str) -> str:
    """Very small rule-based AI brain."""
    text = text.lower()
    greetings = ["hi", "hello", "hey", "yo"]
    if any(word in text for word in greetings):
        return random.choice(["Hey there 👋", "Hello boss!", "Yo! Ready to trade 💹"])
    if "how" in text and "you" in text:
        return random.choice(["I’m good and watching the charts 📈", "Doing fine, markets are moving fast!"])
    if "signal" in text:
        return "📊 I’ll drop a signal automatically once I detect a trend change."
    if "help" in text:
        return "You can say:\n/start – activate bot\nsignal – ask about signals\nhelp – show this message"
    return random.choice([
        "Still learning from the charts 😎",
        "Market data loading... patience pays 📉📈",
        "Hmm, not sure about that — but I’m watching EUR/USD closely!"
    ])


@app.route("/", methods=["GET"])
def home():
    return "Forex Bot Running...", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram messages."""
    data = request.json or {}
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip()

        if text.startswith("/start"):
            send_telegram("🔥 Bot active! Ready to send Forex signals.", chat_id)
        else:
            reply = simple_ai_response(text)
            send_telegram(reply, chat_id)
    return jsonify({"status": "ok"}), 200


def start_thread():
    """Start price monitoring thread."""
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()


def setup_webhook():
    """Automatically register webhook on startup."""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            params={"url": WEBHOOK_URL},
            timeout=10
        )
        if r.ok:
            print(f"✅ Webhook set to {WEBHOOK_URL}")
        else:
            print(f"⚠️ Failed to set webhook: {r.text}")
    except Exception as e:
        print("Webhook setup error:", e)


if __name__ == "__main__":
    setup_webhook()   # auto setup
    start_thread()    # start price monitoring
    app.run(host="0.0.0.0", port=8080)