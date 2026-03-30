from telegram_sender import TelegramSender
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    sender = TelegramSender(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    test_signal = {
        'symbol': 'TEST',
        'direction': 'BUY',
        'bias': 'bullish',
        'poi': 12345.67,
        'confirmation_pattern': 'engulfing',
        'entry': 12345.67,
        'sl': 12300.00,
        'tp1': 12400.00,
        'tp2': 12450.00,
        'tp3': 12500.00,
        'rr': 1.5
    }
    if sender.send_signal(test_signal):
        print("✅ Test message sent successfully.")
    else:
        print("❌ Failed to send test message.")
else:
    print("❌ Telegram credentials not found in .env file. Please add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
