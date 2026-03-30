import time
import logging
import threading
import pandas as pd
from datetime import datetime

from data_fetcher import DataFetcher
from bias_engine import determine_overall_bias
from poi_discovery import POIDiscovery
from focus_manager import FocusManager
from confirmation import detect_confirmation
from trade_plan import TradePlanner
from volatility import calculate_atr
from strategy_config import BTCUSD_CONFIG, ETHUSD_CONFIG, XAUUSD_CONFIG
from telegram_sender import TelegramSender
from trade_manager import TradeManager
import shared_data
from dashboard import start_dashboard
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

def get_last_candle_time(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return int(df.index[-1].timestamp())

def main():
    # Start dashboard in background
    start_dashboard()

    # Initialize Telegram sender if credentials provided
    telegram = TelegramSender(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) if TELEGRAM_BOT_TOKEN else None

    # Trade manager
    trade_manager = TradeManager()

    fetcher = DataFetcher()

    # Build components per symbol
    components = {}
    for sym, cfg in [('BTCUSD', BTCUSD_CONFIG), ('ETHUSD', ETHUSD_CONFIG), ('XAUUSD', XAUUSD_CONFIG)]:
        components[sym] = {
            'poi': POIDiscovery(cfg),
            'focus': FocusManager(cfg),
            'planner': TradePlanner(cfg),
            'config': cfg,
            'last_trade': {'direction': None, 'timestamp': None}
        }

    last_5m_candle_time = {'BTCUSD': 0, 'ETHUSD': 0, 'XAUUSD': 0}
    active_poi_state = {'BTCUSD': {'touch_idx': None, 'processed': False},
                        'ETHUSD': {'touch_idx': None, 'processed': False},
                        'XAUUSD': {'touch_idx': None, 'processed': False}}

    logging.info("Trading bot started. Waiting for new 5m candles...")

    while True:
        try:
            time.sleep(30)

            # Fetch data for all symbols
            btc_data = {}
            eth_data = {}
            xau_data = {}
            for tf in ["15m", "5m", "3m"]:
                btc_data[tf] = fetcher.fetch_btc(tf)
                time.sleep(0.5)
                eth_data[tf] = fetcher.fetch_eth(tf)
                time.sleep(0.5)
                xau_data[tf] = fetcher.fetch_xau(tf)
                time.sleep(0.5)

            # Bias detection
            bias_result = determine_overall_bias(btc_data, eth_data, xau_data)

            # Update trade manager for each symbol using latest 3m close
            now = datetime.now()
            for symbol in ['BTCUSD', 'ETHUSD', 'XAUUSD']:
                if symbol == 'BTCUSD':
                    df = btc_data['3m']
                elif symbol == 'ETHUSD':
                    df = eth_data['3m']
                else:
                    df = xau_data['3m']
                if df is not None and not df.empty:
                    current_price = df['close'].iloc[-1]
                    trade_manager.update(symbol, current_price, now, telegram)

            for symbol in ['BTCUSD', 'ETHUSD', 'XAUUSD']:
                cfg = components[symbol]['config']
                poi = components[symbol]['poi']
                focus = components[symbol]['focus']
                planner = components[symbol]['planner']
                last_trade = components[symbol]['last_trade']

                # Select appropriate data
                if symbol == 'BTCUSD':
                    df_5m = btc_data['5m']
                    df_3m = btc_data['3m']
                    df_15m = btc_data['15m']
                elif symbol == 'ETHUSD':
                    df_5m = eth_data['5m']
                    df_3m = eth_data['3m']
                    df_15m = eth_data['15m']
                else:
                    df_5m = xau_data['5m']
                    df_3m = xau_data['3m']
                    df_15m = xau_data['15m']

                if df_5m is None or df_5m.empty:
                    continue

                current_candle_time = get_last_candle_time(df_5m)
                if current_candle_time > last_5m_candle_time[symbol]:
                    last_5m_candle_time[symbol] = current_candle_time
                    current_price = df_5m['close'].iloc[-1]
                    bias = bias_result.get(symbol, {}).get('bias', 'unclear')

                    if bias in ['bullish', 'bearish']:
                        candidates = poi.get_candidates(df_5m, bias, current_price, df_15m=df_15m)
                        focus.update(current_price, candidates, bias)
                        state = focus.get_state()
                        logging.info(f"[{symbol}] Bias: {bias}, Active: {state['active_poi']}, Watchlist: {state['watchlist']}")

                        current_active = state['active_poi']
                        if current_active is None:
                            active_poi_state[symbol] = {'touch_idx': None, 'processed': False}
                        else:
                            if active_poi_state[symbol]['touch_idx'] is None and current_active is not None:
                                # Find touch index in 3m
                                touch_idx = None
                                for i in range(len(df_3m)-1, -1, -1):
                                    candle = df_3m.iloc[i]
                                    if (bias == 'bullish' and candle['low'] <= current_active) or \
                                       (bias == 'bearish' and candle['high'] >= current_active):
                                        touch_idx = i
                                        break
                                if touch_idx is not None:
                                    active_poi_state[symbol] = {'touch_idx': touch_idx, 'processed': False}
                                else:
                                    active_poi_state[symbol] = {'touch_idx': None, 'processed': False}
                    else:
                        logging.info(f"[{symbol}] Bias unclear, no POI update.")

                # Check for confirmation on active POI
                state = focus.get_state()
                current_active = state['active_poi']
                if (current_active is not None and
                    active_poi_state[symbol]['touch_idx'] is not None and
                    not active_poi_state[symbol]['processed']):
                    # Use the appropriate 3m dataframe
                    if symbol == 'BTCUSD':
                        df_confirm = btc_data['3m']
                    elif symbol == 'ETHUSD':
                        df_confirm = eth_data['3m']
                    else:
                        df_confirm = xau_data['3m']

                    if df_confirm is not None and not df_confirm.empty:
                        direction = bias_result.get(symbol, {}).get('bias', 'unclear')
                        if direction in ['bullish', 'bearish']:
                            touch_idx = active_poi_state[symbol]['touch_idx']
                            if len(df_confirm) - touch_idx > 1:
                                conf = detect_confirmation(
                                    df_confirm, touch_idx, current_active, direction,
                                    config=cfg
                                )
                                if conf:
                                    # Volatility filter
                                    df_5m_up_to = df_5m[df_5m.index <= df_confirm.index[-1]]
                                    if len(df_5m_up_to) >= cfg.get("VOLATILITY_ATR_PERIOD", 20):
                                        atr = calculate_atr(df_5m_up_to.tail(cfg.get("VOLATILITY_ATR_PERIOD", 20)),
                                                            period=cfg.get("VOLATILITY_ATR_PERIOD", 20))
                                        atr_pct = atr / df_confirm.iloc[conf['index']]['close']
                                        if atr_pct < cfg.get("VOLATILITY_MIN_ATR_PCT", 0.0):
                                            logging.info(f"[{symbol}] Skipped due to low volatility")
                                            active_poi_state[symbol]['processed'] = True
                                            continue

                                    plan = planner.build_plan(
                                        df_confirm, touch_idx, current_active, direction,
                                        confirmation_idx=conf['index']
                                    )
                                    if plan is not None:
                                        signal = {
                                            'symbol': symbol,
                                            'direction': direction,
                                            'bias': bias_result.get(symbol, {}).get('bias', 'unclear'),
                                            'poi': current_active,
                                            'confirmation_pattern': conf['pattern'],
                                            'entry': plan['entry'],
                                            'sl': plan['sl'],
                                            'tp1': plan['tp1'],
                                            'tp2': plan['tp2'],
                                            'tp3': plan['tp3'],
                                            'rr': plan['rr']
                                        }
                                        # Store signal for dashboard
                                        shared_data.recent_signals.append({
                                            'time': datetime.now(),
                                            'symbol': symbol,
                                            'direction': direction,
                                            'entry': plan['entry'],
                                            'confirmation_pattern': conf['pattern']
                                        })
                                        if telegram:
                                            telegram.send_signal(signal)
                                        # Add trade to manager
                                        trade_manager.add_trade(signal)
                                        logging.info(f"[{symbol}] Confirmation: {conf['pattern']}")
                                        logging.info(f"[{symbol}] Trade plan: {plan}")
                                        active_poi_state[symbol]['processed'] = True
                                    else:
                                        logging.info(f"[{symbol}] Trade skipped: RR below minimum")
                                        active_poi_state[symbol]['processed'] = True

            # Update shared data for dashboard
            shared_data.active_trades = trade_manager.active_trades
            shared_data.closed_trades = trade_manager.closed_trades

        except Exception as e:
            logging.exception(f"Unexpected error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()