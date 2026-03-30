import requests
import logging

class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_signal(self, signal: dict) -> bool:
        """
        signal should contain:
            symbol, direction, bias, poi, confirmation_pattern,
            entry, sl, tp1, tp2, tp3, rr
        """
        text = (
            f"📊 *{signal['symbol']} SIGNAL*\n\n"
            f"🔹 *Direction:* {signal['direction'].upper()}\n"
            f"📈 *Bias:* {signal['bias']}\n"
            f"📍 *POI:* {signal['poi']:.2f}\n"
            f"✅ *Confirmation:* {signal['confirmation_pattern']}\n\n"
            f"💰 *Entry:* {signal['entry']:.2f}\n"
            f"🛑 *Stop Loss:* {signal['sl']:.2f}\n"
            f"🎯 *TP1:* {signal['tp1']:.2f}\n"
            f"🎯 *TP2:* {signal['tp2']:.2f}\n"
            f"🎯 *TP3:* {signal['tp3']:.2f}\n\n"
            f"📊 *Risk/Reward:* {signal['rr']:.2f}\n\n"
            f"⚡ *Trade with discipline. Manage risk.*"
        )
        return self.send_message(text)

    def send_message(self, text: str) -> bool:
        """Send a plain text message."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            resp = requests.post(self.base_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logging.info("Telegram message sent")
                return True
            else:
                logging.error(f"Telegram error: {resp.text}")
                return False
        except Exception as e:
            logging.error(f"Telegram send failed: {e}")
            return False