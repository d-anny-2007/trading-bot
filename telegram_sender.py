import html
import logging
from datetime import datetime
from typing import Dict, Tuple

import requests


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    @staticmethod
    def _is_bullish(direction: str) -> bool:
        d = str(direction or "").lower()
        return d in {"bullish", "buy", "long", "up"}

    @staticmethod
    def _symbol_code(symbol: str) -> str:
        raw = str(symbol or "").upper().replace("/", "").replace("-", "").replace("_", "")
        if raw.startswith("BTC"):
            return "BTC"
        if raw.startswith("ETH"):
            return "ETH"
        if raw.startswith("XAU"):
            return "XAU"
        if raw.startswith("XAG"):
            return "XAG"
        if raw:
            return raw[:4]
        return "TRD"

    @staticmethod
    def _fmt_num(value) -> str:
        try:
            return f"{float(value):,.2f}"
        except Exception:
            return html.escape(str(value))

    def _direction_meta(self, direction: str) -> Tuple[str, str, str]:
        if self._is_bullish(direction):
            return "🟢", "BULLISH", "BUY"
        return "🔴", "BEARISH", "SELL"

    def _trade_ref(self, trade: dict) -> str:
        symbol_code = self._symbol_code(trade.get("symbol"))
        direction = "BULL" if self._is_bullish(trade.get("direction")) else "BEAR"
        entry_time = trade.get("entry_time")
        if isinstance(entry_time, datetime):
            stamp = entry_time.strftime("%Y%m%d-%H%M")
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
        trade_id = trade.get("trade_id")
        if trade_id is None:
            return f"GS-{symbol_code}-{direction}-{stamp}"
        return f"GS-{symbol_code}-{direction}-{stamp}-{int(trade_id):03d}"

    def _trade_label(self, trade: dict) -> str:
        direction = self._direction_meta(trade.get("direction"))[1]
        symbol = html.escape(str(trade.get("symbol", "UNKNOWN")).upper())
        entry_time = trade.get("entry_time")
        if isinstance(entry_time, datetime):
            ts = entry_time.strftime("%Y-%m-%d %H:%M")
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"{symbol} • {direction} • {ts}"

    def send_signal(self, signal: dict) -> bool:
        """
        signal should contain:
            symbol, direction, bias, poi, confirmation_pattern,
            entry, sl, tp1, tp2, tp3, rr
        """
        dir_emoji, dir_label, _ = self._direction_meta(signal.get("direction"))
        trade_ref = signal.get("trade_ref") or self._trade_ref(signal)
        trade_label = signal.get("trade_label") or self._trade_label(signal)

        symbol = html.escape(str(signal.get("symbol", "UNKNOWN")).upper())
        bias = html.escape(str(signal.get("bias", "unclear")))
        confirmation = html.escape(str(signal.get("confirmation_pattern", "unknown")))

        text = (
            f"🚨 <b>NEW SIGNAL</b>\n"
            f"{dir_emoji} <b>{symbol} • {dir_label}</b>\n"
            f"<code>{html.escape(trade_ref)}</code>\n"
            f"<i>{html.escape(trade_label)}</i>\n\n"
            f"⏳ <b>Act fast.</b> Setup is live now.\n\n"
            f"━━━━━━━━━━━━\n"
            f"<b>TRADE LEVELS</b>\n"
            f"🎯 <b>Entry:</b> <code>{self._fmt_num(signal.get('entry'))}</code>\n"
            f"🛑 <b>SL:</b> <code>{self._fmt_num(signal.get('sl'))}</code>\n"
            f"✅ <b>TP1:</b> <code>{self._fmt_num(signal.get('tp1'))}</code>\n"
            f"✅ <b>TP2:</b> <code>{self._fmt_num(signal.get('tp2'))}</code>\n"
            f"🏁 <b>TP3:</b> <code>{self._fmt_num(signal.get('tp3'))}</code>\n"
            f"📊 <b>RR:</b> <code>{self._fmt_num(signal.get('rr'))}</code>\n\n"
            f"━━━━━━━━━━━━\n"
            f"<b>SETUP CONTEXT</b>\n"
            f"📈 <b>Bias:</b> <code>{bias}</code>\n"
            f"📍 <b>POI:</b> <code>{self._fmt_num(signal.get('poi'))}</code>\n"
            f"🧩 <b>Confirm:</b> <code>{confirmation}</code>\n"
        )
        return self.send_message(text)

    def send_update(self, event_type: str, trade: dict) -> bool:
        """Send a formatted update message for trade events."""
        event = str(event_type or "").upper()
        dir_emoji, dir_label, _ = self._direction_meta(trade.get("direction"))
        trade_ref = trade.get("trade_ref") or self._trade_ref(trade)
        trade_label = trade.get("trade_label") or self._trade_label(trade)
        symbol = html.escape(str(trade.get("symbol", "UNKNOWN")).upper())

        if event == "SL":
            headline = "❌ <b>TRADE CLOSED</b>"
            status = "SL HIT"
            status_emoji = "❌"
            extra = f"📉 <b>Result:</b> <code>SL</code>"
        elif event == "TP1":
            headline = "🔔 <b>TRADE UPDATE</b>"
            status = "TP1 HIT"
            status_emoji = "✅"
            extra = "🔒 <b>Status:</b> SL moved to BE"
        elif event == "TP2":
            headline = "🔔 <b>TRADE UPDATE</b>"
            status = "TP2 HIT"
            status_emoji = "✅"
            extra = "📌 <b>Status:</b> Trade is progressing"
        elif event == "TP3":
            headline = "🏁 <b>TRADE CLOSED</b>"
            status = "TP3 HIT"
            status_emoji = "🏁"
            extra = f"💰 <b>Result:</b> <code>TP3</code>"
        elif event == "BE_MOVED":
            headline = "🔒 <b>TRADE UPDATE</b>"
            status = "SL MOVED TO BE"
            status_emoji = "🔒"
            extra = f"📌 <b>Status:</b> Break-even locked"
        else:
            return False

        text = (
            f"{headline}\n"
            f"{dir_emoji} <b>{symbol} • {dir_label}</b>\n"
            f"<code>{html.escape(trade_ref)}</code>\n"
            f"<i>{html.escape(trade_label)}</i>\n\n"
            f"{status_emoji} <b>{status}</b>\n\n"
            f"━━━━━━━━━━━━\n"
            f"<b>TRADE DETAILS</b>\n"
            f"🎯 <b>Entry:</b> <code>{self._fmt_num(trade.get('entry'))}</code>\n"
            f"🛑 <b>SL:</b> <code>{self._fmt_num(trade.get('sl'))}</code>\n"
            f"✅ <b>TP1:</b> <code>{self._fmt_num(trade.get('tp1'))}</code>\n"
            f"✅ <b>TP2:</b> <code>{self._fmt_num(trade.get('tp2'))}</code>\n"
            f"🏁 <b>TP3:</b> <code>{self._fmt_num(trade.get('tp3'))}</code>\n"
            f"📊 <b>RR:</b> <code>{self._fmt_num(trade.get('rr'))}</code>\n\n"
            f"{extra}"
        )

        if event == "SL" and trade.get("exit_price") is not None:
            text += f"\n🧾 <b>Exit Price:</b> <code>{self._fmt_num(trade.get('exit_price'))}</code>"
        elif event in {"TP1", "TP2", "TP3"} and trade.get("exit_price") is not None:
            text += f"\n🧾 <b>Hit Price:</b> <code>{self._fmt_num(trade.get('exit_price'))}</code>"

        return self.send_message(text)

    def send_message(self, text: str) -> bool:
        """Send a plain text message."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(self.base_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logging.info("Telegram message sent")
                return True
            logging.error(f"Telegram error: {resp.text}")
            return False
        except Exception as e:
            logging.error(f"Telegram send failed: {e}")
            return False