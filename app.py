# app.py
from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ====== TELEGRAM CONFIGURATION ======
# These values will come from Render environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")       # your bot token
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")   # your numeric Telegram ID

def send_telegram(text: str):
    """Send a message via Telegram bot"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

@app.route("/", methods=["GET"])
def root():
    return "🚀 YoungstarFXBot webhook is alive!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive TradingView JSON and forward to Telegram"""
    data = request.json or {}
    try:
        action = data.get("action") or data.get("side", "")
        symbol = data.get("symbol") or data.get("ticker", "EUR/USD")
        price = data.get("price", "")
        sl = data.get("sl", "")
        tp = data.get("tp", "")
        msg = f"💹 <b>{action.upper()}</b> {symbol} @ {price}\n🎯 TP: {tp} | 🛑 SL: {sl}"
        send_telegram(msg)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        send_telegram(f"⚠️ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)