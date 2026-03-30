import pandas as pd
import numpy as np

def calculate_atr(df: pd.DataFrame, period: int = 20) -> float:
    """Calculate the Average True Range for the last `period` candles."""
    if len(df) < period:
        return 0.0
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    tr = np.zeros(len(df))
    for i in range(1, len(df)):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i-1]),
                    abs(low[i] - close[i-1]))
    atr = np.mean(tr[-period:])
    return atr