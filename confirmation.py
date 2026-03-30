import pandas as pd
import numpy as np
from typing import Dict, Optional

def is_engulfing(candle_prev: pd.Series, candle_curr: pd.Series, direction: str,
                 close_beyond_poi: bool = False, poi: float = None) -> bool:
    """Check if current candle engulfs previous in the given direction."""
    if direction == 'bullish':
        engulf = (candle_curr['close'] > candle_curr['open'] and
                  candle_curr['open'] < candle_prev['close'] and
                  candle_curr['close'] > candle_prev['open'])
        if engulf and close_beyond_poi and poi is not None:
            return candle_curr['close'] > poi
        return engulf
    else:
        engulf = (candle_curr['close'] < candle_curr['open'] and
                  candle_curr['open'] > candle_prev['close'] and
                  candle_curr['close'] < candle_prev['open'])
        if engulf and close_beyond_poi and poi is not None:
            return candle_curr['close'] < poi
        return engulf

def is_rejection(candle: pd.Series, direction: str, min_ratio: float = 1.5) -> bool:
    """
    Detects a rejection candle at the POI.
    For bullish: long lower wick (rejection of downside)
    For bearish: long upper wick (rejection of upside)
    """
    body = abs(candle['close'] - candle['open'])
    if body == 0:
        return False
    if direction == 'bullish':
        wick = min(candle['open'], candle['close']) - candle['low']
        return wick > body * min_ratio
    else:
        wick = candle['high'] - max(candle['open'], candle['close'])
        return wick > body * min_ratio

def is_sweep_reclaim(df: pd.DataFrame, idx: int, poi: float, direction: str,
                     close_beyond_poi: bool = True) -> bool:
    """
    Sweep & reclaim pattern:
      - Sweep: price briefly breaks the POI (below for bullish, above for bearish)
      - Reclaim: the next candle closes back beyond the POI
    """
    if idx < 1:
        return False
    candle_prev = df.iloc[idx-1]
    candle_curr = df.iloc[idx]
    if direction == 'bullish':
        sweep = candle_prev['low'] < poi
        reclaim = candle_curr['close'] > poi
        if close_beyond_poi:
            return sweep and reclaim and candle_curr['close'] > poi
        return sweep and reclaim
    else:
        sweep = candle_prev['high'] > poi
        reclaim = candle_curr['close'] < poi
        if close_beyond_poi:
            return sweep and reclaim and candle_curr['close'] < poi
        return sweep and reclaim

def is_structure_break(df: pd.DataFrame, idx: int, direction: str, lookback: int = 3) -> bool:
    """
    Structure break after POI touch:
      - For bullish: price makes a higher high than the last lookback candles
      - For bearish: price makes a lower low than the last lookback candles
    """
    if idx < lookback:
        return False
    recent = df.iloc[idx-lookback:idx+1]
    if direction == 'bullish':
        recent_high = recent['high'].max()
        return df.iloc[idx]['high'] > recent_high
    else:
        recent_low = recent['low'].min()
        return df.iloc[idx]['low'] < recent_low

def is_evening_star(df: pd.DataFrame, idx: int, direction: str) -> bool:
    """
    Evening star (bearish reversal) pattern:
      - A large bullish candle
      - A small candle (doji or spinning top)
      - A large bearish candle that closes below the midpoint of the first candle
    """
    if idx < 2:
        return False
    first = df.iloc[idx-2]
    second = df.iloc[idx-1]
    third = df.iloc[idx]
    if direction != 'bearish':
        return False
    # First candle bullish
    if first['close'] <= first['open']:
        return False
    # Second candle small (body less than 0.5% of first candle's body)
    first_body = abs(first['close'] - first['open'])
    second_body = abs(second['close'] - second['open'])
    if second_body > first_body * 0.5:
        return False
    # Third candle bearish and closes below midpoint of first candle
    if third['close'] >= third['open']:
        return False
    midpoint = (first['high'] + first['low']) / 2
    return third['close'] < midpoint

def detect_confirmation(df: pd.DataFrame, touch_idx: int, poi: float, direction: str,
                        config: dict) -> Optional[Dict]:
    """
    After POI touch, analyze up to max_candles candles for confirmation patterns.
    Returns dict with pattern name and the candle index where confirmation occurred,
    or None if none found.
    """
    max_candles = config.get("CONFIRMATION_MAX_CANDLES", 5)
    max_distance_pct = config.get("CONFIRMATION_MAX_DISTANCE_PCT", 0.002)
    engulfing_close_beyond = config.get("CONFIRMATION_ENGULFING_CLOSE_BEYOND_POI", False)
    rejection_min_ratio = config.get("CONFIRMATION_REJECTION_MIN_BODY_WICK_RATIO", 1.5)
    sweep_reclaim_close_beyond = config.get("CONFIRMATION_SWEEP_RECLAIM_CLOSE_BEYOND_POI", False)

    end_idx = min(touch_idx + max_candles, len(df)-1)
    for i in range(touch_idx, end_idx+1):
        candle = df.iloc[i]
        # Check distance from POI
        if direction == 'bullish':
            dist = abs(candle['low'] - poi) / poi
        else:
            dist = abs(candle['high'] - poi) / poi
        if dist > max_distance_pct:
            continue

        # Evening star (only bearish)
        if direction == 'bearish' and i >= 2 and is_evening_star(df, i, direction):
            return {'pattern': 'evening_star', 'index': i}

        # Structure break
        if is_structure_break(df, i, direction):
            return {'pattern': 'structure_break', 'index': i}

        # Rejection
        if is_rejection(candle, direction, min_ratio=rejection_min_ratio):
            return {'pattern': 'rejection', 'index': i}

        # Sweep & reclaim (needs previous candle)
        if i > 0 and is_sweep_reclaim(df, i, poi, direction,
                                      close_beyond_poi=sweep_reclaim_close_beyond):
            return {'pattern': 'sweep_reclaim', 'index': i}

        # Engulfing (needs previous candle)
        if i > 0 and is_engulfing(df.iloc[i-1], candle, direction,
                                  close_beyond_poi=engulfing_close_beyond, poi=poi):
            return {'pattern': 'engulfing', 'index': i}

    return None