# app.py
import json
import time
import threading
import requests
from collections import deque
from flask import Flask, request, jsonify
import random
import os

# Optional: import OpenAI client only if available
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# Load settings from config.json (safe fallback if env not used)
config = {}
if os.path.exists("config.json"):
    with open("config.json", "r") as f:
        config = json.load(f)

# Prefer environment variables (safer on hosts like Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or config.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or config.get("TELEGRAM_CHAT_ID")
FOREX_API_KEY = os.getenv("FOREX_API_KEY") or config.get("FOREX_API_KEY", "")
FOREX_API_URL = os.getenv("FOREX_API_URL") or config.get("FOREX_API_URL", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL") or config.get("POLL_INTERVAL", 300))
SHORT_WINDOW = int(os.getenv("SHORT_WINDOW") or config.get("SHORT_WINDOW", 3))
LONG_WINDOW = int(os.getenv("LONG_WINDOW") or config.get("LONG_WINDOW", 8))
SYMBOL = os.getenv("SYMBOL") or config.get("SYMBOL", "EUR/USD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or config.get("OPENAI_API_KEY", "")

# Setup OpenAI if key available
if OPENAI_API_KEY and OPENAI_AVAILABLE:
    openai.api_key = OPENAI_API_KEY
elif OPENAI_API_KEY and not OPENAI_AVAILABLE:
    print("OpenAI key provided but openai library is not installed. Install 'openai' in requirements.")

app = Flask(__name__)
price_history = deque(maxlen=LONG_WINDOW + 2)
last_signal = {"side": None, "price": None}

# Replace TELEGRAM_CHAT_ID with string or integer as needed
def send_telegram(text: str, chat_id: str = None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID
    if not TELEGRAM_TOKEN or not chat_id:
        print("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID; cannot send message.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok:
            print("Telegram API error:", r.status_code, r.text)
        return r.ok
    except Exception as e:
        print("Telegram send error:", e)
        return False

def fetch_price():
    try:
        if FOREX_API_URL:
            r = requests.get(FOREX_API_URL, params={"apikey": FOREX_API_KEY}, timeout=10)
            r.raise_for_status()
            data = r.json()
            # adapt provider field names if needed
            return float(data.get("price") or data.get("rate") or data.get("last") or data.get("close"))
        else:
            r = requests.get("https://api.exchangerate.host/latest?base=EUR&symbols=USD", timeout=10)
            r.raise_for_status()
            return float(r.json()["rates"]["USD"])
    except Exception as e:
        print("Fetch price error:", e)
        return None

def compute_sma(prices, window):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window

def generate_signal():
    if len(price_history) < LONG_WINDOW:
        return None, None
    prices = list(price_history)
    short_sma = compute_sma(prices, SHORT_WINDOW)
    long_sma = compute_sma(prices, LONG_WINDOW)
    current_price = prices[-1]
    if short_sma is None or long_sma is None:
        return None, None
    if short_sma > long_sma and last_signal["side"] != "BUY":
        return "BUY", current_price
    elif short_sma < long_sma and last_signal["side"] != "SELL":
        return "SELL", current_price
    else:
        return None, None

def polling_loop():
    print("📡 Polling started...")
    while True:
        price = fetch_price()
        if price:
            price_history.append(price)
            print("EUR/USD =", price)
            side, p = generate_signal()
            if side:
                tp = round(p + 0.0030, 5) if side == "BUY" else round(p - 0.0030, 5)
                sl = round(p - 0.0020, 5) if side == "BUY" else round(p + 0.0020, 5)
                msg = f"💹 <b>{side}</b> {SYMBOL} @ {p}\n🎯 TP: {tp} | 🛑 SL: {sl}\n🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC"
                send_telegram(msg)
                last_signal.update({"side": side, "price": p})
        else:
            print("Failed to fetch price.")
        time.sleep(POLL_INTERVAL)

def simple_ai_response(text: str) -> str:
    text = (text or "").lower()
    greetings = ["hi","hello","hey","yo"]
    if any(g in text for g in greetings):
        return random.choice(["Hey there 👋", "Hello boss!", "Yo — I'm watching the charts!"])
    if "how" in text and "you" in text:
        return random.choice(["I’m good and watching the charts 📈", "Fine — markets moving, boss."])
    if "signal" in text:
        return "📊 I send signals automatically when the SMA crossover triggers. You can also ask 'why buy' or 'why sell'."
    if "help" in text:
        return "Commands: /start, /signal (latest), help. Ask market questions like: 'Why is EURUSD rising?'"
    return random.choice(["Still learning from the charts 😎", "Market data loading... patience pays 📉📈"])

def ask_openai(prompt: str) -> str:
    """Ask OpenAI if available; fallback otherwise."""
    if not OPENAI_API_KEY or not OPENAI_AVAILABLE:
        return simple_ai_response(prompt)
    try:
        # Using chat completion API (ChatCompletions). Adjust model name if needed.
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # change model if you want / have access
            messages=[
                {"role":"system","content":"You are NBforexBot, a helpful professional forex trading assistant. Keep answers short and clear."},
                {"role":"user","content": prompt}
            ],
            max_tokens=400,
            temperature=0.3
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("OpenAI call error:", e)
        return simple_ai_response(prompt)

@app.route("/", methods=["GET"])
def home():
    return "Forex Bot running", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True) or {}
    # Telegram update with message
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip()
        if text.startswith("/start"):
            send_telegram("🔥 Bot active! I’ll send signals and can answer your market questions.", chat_id)
            return jsonify({"status":"ok"}), 200
        if text.startswith("/signal"):
            # send last known signal or info
            side = last_signal.get("side")
            price = last_signal.get("price")
            if side and price:
                send_telegram(f"Last signal: <b>{side}</b> {SYMBOL} @ {price}", chat_id)
            else:
                send_telegram("No signal yet. Wait for market conditions.", chat_id)
            return jsonify({"status":"ok"}), 200

        # ask OpenAI (if available) or fallback
        reply = ask_openai(text)
        send_telegram(reply, chat_id)
        return jsonify({"status":"ok"}), 200

    # If call not from Telegram (e.g., manual webhook test), just acknowledge
    return jsonify({"status":"ok"}), 200

def setup_webhook():
    """Register webhook with Telegram on startup (use your Render URL)."""
    webhook_url = os.getenv("WEBHOOK_URL") or config.get("WEBHOOK_URL") or ""
    if not webhook_url:
        print("WEBHOOK_URL not set; skip webhook registration.")
        return
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
                         params={"url": webhook_url}, timeout=10)
        print("setWebhook response:", r.status_code, r.text)
    except Exception as e:
        print("Webhook setup error:", e)

if __name__ == "__main__":
    # start polling thread
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    # try to auto-register webhook (if WEBHOOK_URL provided in env or config)
    setup_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))