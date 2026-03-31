import ccxt
import requests
import pandas as pd
import time
from typing import Optional
from config import CANDLE_LIMIT
from config import ALPHA_VANTAGE_KEY
self.alpha_vantage_key = ALPHA_VANTAGE_KEY

class DataFetcher:
    def __init__(self):
        # Use KuCoin (often accessible from many regions)
        self.kucoin = ccxt.kucoin()
        # Cache for XAU 1min data
        self._xau_1min_cache = None
        self._xau_1min_cache_time = 0
        self._xau_cache_ttl = 600  # seconds (10 minutes)
        self.alpha_vantage_key = None  # set via .env

    def fetch_btc(self, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self.kucoin.fetch_ohlcv(
                "BTC/USDT", timeframe, limit=CANDLE_LIMIT
            )
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching BTC {timeframe}: {e}")
            return None

    def fetch_eth(self, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self.kucoin.fetch_ohlcv(
                "ETH/USDT", timeframe, limit=CANDLE_LIMIT
            )
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching ETH {timeframe}: {e}")
            return None

    def fetch_xau(self, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch XAUUSD data using Alpha Vantage."""
        if not self.alpha_vantage_key:
            print("Alpha Vantage API key not set. Skipping XAU.")
            return None

        # Only fetch once per cache_ttl and resample to needed timeframe
        now = time.time()
        if self._xau_1min_cache is None or (now - self._xau_1min_cache_time) > self._xau_cache_ttl:
            # Fetch 1min data from Alpha Vantage
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": "XAUUSD",
                "interval": "1min",
                "outputsize": "full",
                "apikey": self.alpha_vantage_key,
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    print(f"Alpha Vantage error: {resp.text}")
                    return None
                data = resp.json()
                if "Time Series (1min)" not in data:
                    print(f"Unexpected Alpha Vantage response: {data}")
                    return None
                series = data["Time Series (1min)"]
                rows = []
                for ts, values in series.items():
                    rows.append({
                        "timestamp": pd.to_datetime(ts),
                        "open": float(values["1. open"]),
                        "high": float(values["2. high"]),
                        "low": float(values["3. low"]),
                        "close": float(values["4. close"]),
                        "volume": float(values["5. volume"]),
                    })
                df = pd.DataFrame(rows)
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                # Keep only last 2000 candles to save memory
                df = df.tail(2000)
                self._xau_1min_cache = df
                self._xau_1min_cache_time = now
            except Exception as e:
                print(f"Error fetching XAU from Alpha Vantage: {e}")
                return None

        if self._xau_1min_cache is None:
            return None

        # Resample to requested timeframe
        agg_minutes = {"15m": 15, "5m": 5, "3m": 3}[timeframe]
        agg_dict = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }
        resampled = self._xau_1min_cache.resample(f"{agg_minutes}min").agg(agg_dict).dropna()
        resampled = resampled.tail(CANDLE_LIMIT)
        return resampled