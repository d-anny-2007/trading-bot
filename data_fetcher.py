import ccxt
import requests
import pandas as pd
import time
from typing import Dict, Optional
from config import (
    TWELVE_DATA_API_KEY, SYMBOLS, TIMEFRAMES,
    AGGREGATION_MAP, RAW_CANDLE_LIMIT, CANDLE_LIMIT
)

class DataFetcher:
    def __init__(self):
        # Use Bybit (more permissive than Binance)
        self.bybit = ccxt.bybit()
        self.twelve_session = requests.Session()
        self.base_url = "https://api.twelvedata.com/time_series"
        # Cache for XAU 1min data to avoid exhausting Twelve Data credits
        self._xau_1min_cache = None
        self._xau_1min_cache_time = 0

    def fetch_btc(self, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self.bybit.fetch_ohlcv(
                SYMBOLS["BTCUSD"], timeframe, limit=CANDLE_LIMIT
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
            ohlcv = self.bybit.fetch_ohlcv(
                SYMBOLS["ETHUSD"], timeframe, limit=CANDLE_LIMIT
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

    def _fetch_xau_1min(self) -> Optional[pd.DataFrame]:
        """Fetch 1min XAUUSD data from Twelve Data, using cache to avoid rate limits."""
        now = time.time()
        # Cache for 5 minutes to reduce API calls
        if self._xau_1min_cache is not None and (now - self._xau_1min_cache_time) < 300:
            return self._xau_1min_cache

        try:
            params = {
                "symbol": "XAU/USD",
                "interval": "1min",
                "outputsize": RAW_CANDLE_LIMIT,
                "apikey": TWELVE_DATA_API_KEY,
            }
            resp = self.twelve_session.get(self.base_url, params=params)
            if resp.status_code != 200:
                print(f"Twelve Data error: {resp.text}")
                return None
            data = resp.json()
            if "values" not in data:
                print(f"Unexpected response: {data}")
                return None

            df = pd.DataFrame(data["values"])
            rename_dict = {
                "datetime": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
            }
            if "volume" in df.columns:
                rename_dict["volume"] = "volume"
            df = df.rename(columns=rename_dict)

            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            if "volume" in df.columns:
                df["volume"] = df["volume"].astype(float)

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            if "volume" not in df.columns:
                df["volume"] = 0.0

            # Update cache
            self._xau_1min_cache = df
            self._xau_1min_cache_time = now
            return df
        except Exception as e:
            print(f"Error fetching XAU 1min: {e}")
            return None

    def fetch_xau(self, timeframe: str) -> Optional[pd.DataFrame]:
        if timeframe not in AGGREGATION_MAP:
            print(f"Timeframe {timeframe} not supported for aggregation")
            return None

        df_1min = self._fetch_xau_1min()
        if df_1min is None:
            return None

        agg_minutes = AGGREGATION_MAP[timeframe]
        agg_dict = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if "volume" in df_1min.columns:
            agg_dict["volume"] = "sum"
        resampled = df_1min.resample(f"{agg_minutes}min").agg(agg_dict).dropna()
        resampled = resampled.tail(CANDLE_LIMIT)
        return resampled