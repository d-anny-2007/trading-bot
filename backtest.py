import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import ccxt
from tqdm import tqdm

from config import TWELVE_DATA_API_KEY, SYMBOLS
from strategy_config import BTCUSD_CONFIG, ETHUSD_CONFIG, XAUUSD_CONFIG
from bias_engine import determine_overall_bias
from poi_discovery import POIDiscovery
from focus_manager import FocusManager
from confirmation import detect_confirmation
from trade_plan import TradePlanner
from volatility import calculate_atr

class Backtester:
    def __init__(self, symbol: str, start_date: datetime, end_date: datetime, cache_dir='cache'):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        if symbol == 'BTCUSD':
            self.config = BTCUSD_CONFIG
        elif symbol == 'ETHUSD':
            self.config = ETHUSD_CONFIG
        else:
            self.config = XAUUSD_CONFIG

        self.poi_discovery = POIDiscovery(self.config)
        self.focus_manager = FocusManager(self.config)
        self.trade_planner = TradePlanner(self.config)
        self.trades = []
        self.last_trade = {'direction': None, 'timestamp': None}

    def _cache_path(self) -> str:
        return os.path.join(self.cache_dir, f"{self.symbol}_{self.start_date.date()}_{self.end_date.date()}.parquet")

    def _fetch_btc_1min(self) -> pd.DataFrame:
        exchange = ccxt.binance()
        start_ts = int(self.start_date.timestamp() * 1000)
        end_ts = int(self.end_date.timestamp() * 1000)
        all_ohlcv = []
        print("Fetching BTC 1min data...")
        while start_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(SYMBOLS['BTCUSD'], '1m', since=start_ts, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            start_ts = ohlcv[-1][0] + 1
            time.sleep(0.5)
            print(f"  Fetched {len(ohlcv)} bars, latest: {pd.to_datetime(ohlcv[-1][0], unit='ms')}")
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        else:
            df['volume'] = df['volume'].fillna(0.0)
        return df

    def _fetch_eth_1min(self) -> pd.DataFrame:
        exchange = ccxt.binance()
        start_ts = int(self.start_date.timestamp() * 1000)
        end_ts = int(self.end_date.timestamp() * 1000)
        all_ohlcv = []
        print("Fetching ETH 1min data...")
        while start_ts < end_ts:
            ohlcv = exchange.fetch_ohlcv(SYMBOLS['ETHUSD'], '1m', since=start_ts, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            start_ts = ohlcv[-1][0] + 1
            time.sleep(0.5)
            print(f"  Fetched {len(ohlcv)} bars, latest: {pd.to_datetime(ohlcv[-1][0], unit='ms')}")
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        else:
            df['volume'] = df['volume'].fillna(0.0)
        return df

    def _fetch_xau_1min(self) -> pd.DataFrame:
        session = requests.Session()
        base_url = "https://api.twelvedata.com/time_series"
        all_data = []
        current = self.start_date
        print("Fetching XAU 1min data...")
        while current < self.end_date:
            end_chunk = min(current + timedelta(days=3), self.end_date)
            params = {
                'symbol': 'XAU/USD',
                'interval': '1min',
                'start_date': current.strftime('%Y-%m-%d %H:%M:%S'),
                'end_date': end_chunk.strftime('%Y-%m-%d %H:%M:%S'),
                'outputsize': 5000,
                'apikey': TWELVE_DATA_API_KEY
            }
            resp = session.get(base_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if 'values' in data:
                    all_data.extend(data['values'])
                    print(f"  Fetched {len(data['values'])} bars up to {end_chunk}")
                else:
                    print(f"  Unexpected response: {data}")
            else:
                print(f"  Error {resp.status_code}: {resp.text}")
            current = end_chunk
            time.sleep(1)

        df = pd.DataFrame(all_data)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={'datetime': 'timestamp', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close'})
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        else:
            df['volume'] = df['volume'].fillna(0.0)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        return df

    def _load_or_fetch_1min(self) -> pd.DataFrame:
        cache_file = self._cache_path()
        if os.path.exists(cache_file):
            print(f"Loading cached data from {cache_file}")
            return pd.read_parquet(cache_file)

        if self.symbol == 'BTCUSD':
            df = self._fetch_btc_1min()
        elif self.symbol == 'ETHUSD':
            df = self._fetch_eth_1min()
        else:
            df = self._fetch_xau_1min()

        if not df.empty:
            df.to_parquet(cache_file)
        return df

    def run(self):
        print(f"Preparing data for {self.symbol} from {self.start_date} to {self.end_date}...")
        df_1min = self._load_or_fetch_1min()
        if df_1min.empty:
            print("No data fetched.")
            return

        agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        if 'volume' in df_1min.columns:
            agg_dict['volume'] = 'sum'

        print("Resampling data...")
        df_15m = df_1min.resample('15min').agg(agg_dict).dropna()
        df_5m = df_1min.resample('5min').agg(agg_dict).dropna()
        df_3m = df_1min.resample('3min').agg(agg_dict).dropna()

        if len(df_3m) < 200 or len(df_5m) < 200 or len(df_15m) < 200:
            print("Insufficient data after resampling.")
            return

        print(f"Simulating over {len(df_3m)} candles...")
        open_trades = []
        processed = set()

        timestamps_3m = df_3m.index
        highs_3m = df_3m['high'].values
        lows_3m = df_3m['low'].values
        closes_3m = df_3m['close'].values

        for i in tqdm(range(len(df_3m)), desc=f"Processing {self.symbol}"):
            ts = timestamps_3m[i]
            current_price = closes_3m[i]

            df_15m_up_to = df_15m[df_15m.index <= ts]
            df_5m_up_to = df_5m[df_5m.index <= ts]
            df_3m_up_to = df_3m[df_3m.index <= ts]

            if len(df_5m_up_to) < 200 or len(df_15m_up_to) < 200:
                continue

            # Bias detection (pass dummy data for other symbols)
            btc_data = {}
            eth_data = {}
            xau_data = {}
            if self.symbol == 'BTCUSD':
                btc_data = {'15m': df_15m_up_to.tail(200), '5m': df_5m_up_to.tail(200), '3m': df_3m_up_to.tail(200)}
            elif self.symbol == 'ETHUSD':
                eth_data = {'15m': df_15m_up_to.tail(200), '5m': df_5m_up_to.tail(200), '3m': df_3m_up_to.tail(200)}
            else:
                xau_data = {'15m': df_15m_up_to.tail(200), '5m': df_5m_up_to.tail(200), '3m': df_3m_up_to.tail(200)}

            bias_result = determine_overall_bias(btc_data, eth_data, xau_data)
            bias = bias_result.get(self.symbol, {}).get('bias', 'unclear')

            if bias in ['bullish', 'bearish']:
                df_5m_recent = df_5m_up_to.tail(200)
                candidates = self.poi_discovery.get_candidates(df_5m_recent, bias, current_price,
                                                               df_15m=df_15m_up_to if self.config.get("USE_15M_POI_FILTER", False) else None)
                self.focus_manager.update(current_price, candidates, bias)
                state = self.focus_manager.get_state()
                active_poi = state['active_poi']

                if active_poi is not None:
                    touch_idx = None
                    for j in range(i, -1, -1):
                        if (bias == 'bullish' and lows_3m[j] <= active_poi) or \
                           (bias == 'bearish' and highs_3m[j] >= active_poi):
                            touch_idx = j
                            break
                    if touch_idx is not None:
                        key = (active_poi, timestamps_3m[touch_idx])
                        if key not in processed and (i - touch_idx) <= self.config.get("CONFIRMATION_MAX_CANDLES", 5):
                            # Anti‑flip check (disabled for now)
                            conf = detect_confirmation(df_3m_up_to, touch_idx, active_poi, bias, self.config)
                            if conf:
                                # Volatility filter
                                if len(df_5m_up_to) >= self.config.get("VOLATILITY_ATR_PERIOD", 20):
                                    atr = calculate_atr(df_5m_up_to.tail(self.config.get("VOLATILITY_ATR_PERIOD", 20)),
                                                        period=self.config.get("VOLATILITY_ATR_PERIOD", 20))
                                    atr_pct = atr / current_price
                                    if atr_pct < self.config.get("VOLATILITY_MIN_ATR_PCT", 0.0):
                                        continue

                                plan = self.trade_planner.build_plan(
                                    df_3m_up_to, touch_idx, active_poi, bias,
                                    confirmation_idx=conf['index']
                                )
                                if plan is not None:
                                    already = any(t['active_poi'] == active_poi and t['direction'] == bias for t in open_trades)
                                    if not already:
                                        trade = {
                                            'entry_time': timestamps_3m[conf['index']],
                                            'entry': plan['entry'],
                                            'sl': plan['sl'],
                                            'tp1': plan['tp1'],
                                            'tp2': plan['tp2'],
                                            'tp3': plan['tp3'],
                                            'direction': bias,
                                            'active_poi': active_poi,
                                            'confirmation_pattern': conf['pattern'],
                                            'rr': plan['rr']
                                        }
                                        open_trades.append(trade)
                                        processed.add(key)
                                        print(f"[{self.symbol}] Trade opened at {trade['entry_time']}: {bias} at {trade['entry']:.2f}, SL {trade['sl']:.2f}, TP1 {trade['tp1']:.2f}")

            # Check open trades for hits
            for trade in list(open_trades):
                entry_idx = df_3m.index.get_loc(trade['entry_time'])
                if i <= entry_idx:
                    continue
                for j in range(entry_idx+1, i+1):
                    candle = df_3m.iloc[j]
                    if trade['direction'] == 'bullish':
                        if candle['low'] <= trade['sl']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['sl']
                            trade['result'] = 'SL'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['high'] >= trade['tp3']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp3']
                            trade['result'] = 'TP3'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['high'] >= trade['tp2']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp2']
                            trade['result'] = 'TP2'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['high'] >= trade['tp1']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp1']
                            trade['result'] = 'TP1'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                    else:
                        if candle['high'] >= trade['sl']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['sl']
                            trade['result'] = 'SL'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['low'] <= trade['tp3']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp3']
                            trade['result'] = 'TP3'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['low'] <= trade['tp2']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp2']
                            trade['result'] = 'TP2'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break
                        if candle['low'] <= trade['tp1']:
                            trade['exit_time'] = timestamps_3m[j]
                            trade['exit_price'] = trade['tp1']
                            trade['result'] = 'TP1'
                            open_trades.remove(trade)
                            self.trades.append(trade)
                            break

        total_trades = len(self.trades)
        if total_trades == 0:
            print("No trades executed.")
            return

        wins = [t for t in self.trades if t['result'] in ('TP1','TP2','TP3')]
        losses = [t for t in self.trades if t['result'] == 'SL']
        win_count = len(wins)
        loss_count = len(losses)

        def realized_rr(t):
            risk = abs(t['entry'] - t['sl'])
            if t['result'] == 'TP1':
                return abs(t['tp1'] - t['entry']) / risk
            elif t['result'] == 'TP2':
                return abs(t['tp2'] - t['entry']) / risk
            elif t['result'] == 'TP3':
                return abs(t['tp3'] - t['entry']) / risk
            else:
                return -1.0

        for t in self.trades:
            t['realized_rr'] = realized_rr(t)

        total_rr_winners = sum(t['realized_rr'] for t in wins)
        total_rr_losers = sum(abs(t['realized_rr']) for t in losses)
        win_rate = win_count / total_trades * 100
        loss_rate = loss_count / total_trades * 100
        profit_factor = total_rr_winners / total_rr_losers if total_rr_losers > 0 else float('inf')
        avg_rr_win = total_rr_winners / win_count if win_count > 0 else 0

        print(f"\n--- Backtest Results for {self.symbol} ---")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Total trades: {total_trades}")
        print(f"Wins: {win_count} ({win_rate:.2f}%)")
        print(f"Losses: {loss_count} ({loss_rate:.2f}%)")
        print(f"Profit factor: {profit_factor:.2f}")
        print(f"Avg RR per win: {avg_rr_win:.2f}")
        print(f"TP1 hits: {sum(1 for t in wins if t['result']=='TP1')}")
        print(f"TP2 hits: {sum(1 for t in wins if t['result']=='TP2')}")
        print(f"TP3 hits: {sum(1 for t in wins if t['result']=='TP3')}")

if __name__ == "__main__":
    start = datetime(2026, 2, 1)
    end = datetime(2026, 3, 15)
    # Run ETHUSD first
    for sym in ['ETHUSD', 'BTCUSD', 'XAUUSD']:
        bt = Backtester(sym, start, end)
        bt.run()