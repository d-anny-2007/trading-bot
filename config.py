import os
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")

SYMBOLS = {
    "BTCUSD": "BTC/USDT",
    "ETHUSD": "ETH/USDT",
    "XAUUSD": "XAU/USD"
}

TIMEFRAMES = {
    "15m": "15min",
    "5m": "5min",
    "3m": "3min"
}

AGGREGATION_MAP = {
    "15m": 15,
    "5m": 5,
    "3m": 3
}

RAW_CANDLE_LIMIT = 200 * 15
CANDLE_LIMIT = 200

# Default values (overridden by per‑symbol configs)
DEFAULT_MAX_WATCHLIST_SIZE = 3
DEFAULT_EXPIRY_CANDLES = 10
DEFAULT_EXPIRY_DISTANCE_PCT = 0.005

# Telegram settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")