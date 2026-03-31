import ccxt
import requests
import pandas as pd
import time
from typing import Optional
from config import CANDLE_LIMIT

class DataFetcher:
    def __init__(self):
        # Use KuCoin for BTC and ETH (works in your region)
        self.kucoin = ccxt.kucoin()
        self._xau_error_logged = False   # to avoid spamming logs

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
        # Temporarily disabled due to lack of free XAU data source
        if not self._xau_error_logged:
            print("XAU data fetching is currently disabled. No free API available.")
            self._xau_error_logged = True
        return None