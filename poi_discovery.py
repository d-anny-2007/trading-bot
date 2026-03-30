import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional

class POIDiscovery:
    def __init__(self, config: dict):
        self.max_watchlist = config.get("MAX_WATCHLIST_SIZE", 3)
        self.max_distance_pct = config.get("MAX_POI_DISTANCE_PCT", 0.02)
        self.min_distance_pct = config.get("MIN_POI_DISTANCE_PCT", 0.002)
        self.merge_threshold_pct = config.get("MERGE_THRESHOLD_PCT", 0.0005)
        self.swing_strength_pct = config.get("SWING_STRENGTH_PCT", 0.002)
        self.use_15m_filter = config.get("USE_15M_POI_FILTER", False)

    def _is_swing_high(self, highs: np.ndarray, i: int, window: int = 5) -> bool:
        left = max(highs[i-window:i]) if i-window >= 0 else highs[i]
        right = max(highs[i+1:i+window+1]) if i+window < len(highs) else highs[i]
        return highs[i] > left and highs[i] > right and (highs[i] - max(left, right)) / highs[i] >= self.swing_strength_pct

    def _is_swing_low(self, lows: np.ndarray, i: int, window: int = 5) -> bool:
        left = min(lows[i-window:i]) if i-window >= 0 else lows[i]
        right = min(lows[i+1:i+window+1]) if i+window < len(lows) else lows[i]
        return lows[i] < left and lows[i] < right and (min(left, right) - lows[i]) / lows[i] >= self.swing_strength_pct

    def _detect_swings(self, df: pd.DataFrame, window: int = 5) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        highs = df['high'].values
        lows = df['low'].values
        swing_highs = []
        swing_lows = []
        for i in range(window, len(df) - window):
            if self._is_swing_high(highs, i, window):
                swing_highs.append((highs[i], i))
            if self._is_swing_low(lows, i, window):
                swing_lows.append((lows[i], i))
        return swing_highs, swing_lows

    def _detect_protected_levels(self, df: pd.DataFrame, window: int = 5) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        protected_highs = []
        protected_lows = []
        for i in range(window, len(df) - window):
            candle = df.iloc[i]
            body = abs(candle['close'] - candle['open'])
            if body == 0:
                continue
            # Long upper wick
            if candle['high'] - max(candle['open'], candle['close']) > body * 1.5:
                if self._is_swing_high(df['high'].values, i, window):
                    protected_highs.append((candle['high'], i))
            # Long lower wick
            if min(candle['open'], candle['close']) - candle['low'] > body * 1.5:
                if self._is_swing_low(df['low'].values, i, window):
                    protected_lows.append((candle['low'], i))
        return protected_highs, protected_lows

    def _detect_order_blocks(self, df: pd.DataFrame, bias: str) -> List[Tuple[float, int]]:
        ob_candidates = []
        for i in range(1, len(df)):
            prev = df.iloc[i-1]
            curr = df.iloc[i]
            move_pct = abs(curr['close'] - prev['close']) / prev['close']
            if move_pct < 0.002:
                continue
            if bias == 'bullish' and curr['close'] > curr['open'] and prev['close'] < prev['open']:
                ob_candidates.append((prev['low'], i-1))
            elif bias == 'bearish' and curr['close'] < curr['open'] and prev['close'] > prev['open']:
                ob_candidates.append((prev['high'], i-1))
        return ob_candidates

    def _merge_levels(self, levels: List[float], tolerance_pct: float) -> List[float]:
        if not levels:
            return []
        sorted_levels = sorted(levels)
        merged = []
        current = sorted_levels[0]
        for level in sorted_levels[1:]:
            if (level - current) / current <= tolerance_pct:
                current = (current + level) / 2
            else:
                merged.append(current)
                current = level
        merged.append(current)
        return merged

    def _is_swing_high_15m(self, level: float, df_15m: pd.DataFrame) -> bool:
        tolerance = level * 0.001
        for i in range(5, len(df_15m)-5):
            high = df_15m['high'].iloc[i]
            if abs(high - level) / level <= tolerance:
                if self._is_swing_high(df_15m['high'].values, i, window=3):
                    return True
        return False

    def _is_swing_low_15m(self, level: float, df_15m: pd.DataFrame) -> bool:
        tolerance = level * 0.001
        for i in range(5, len(df_15m)-5):
            low = df_15m['low'].iloc[i]
            if abs(low - level) / level <= tolerance:
                if self._is_swing_low(df_15m['low'].values, i, window=3):
                    return True
        return False

    def get_candidates(self, df_5m: pd.DataFrame, bias: str, current_price: float,
                       df_15m: Optional[pd.DataFrame] = None) -> List[Dict]:
        if bias not in ['bullish', 'bearish']:
            return []

        swing_highs, swing_lows = self._detect_swings(df_5m)
        protected_highs, protected_lows = self._detect_protected_levels(df_5m)
        order_blocks = self._detect_order_blocks(df_5m, bias)

        candidates_raw = []
        if bias == 'bullish':
            for level, idx in swing_lows:
                candidates_raw.append((level, idx, 'swing_low'))
            for level, idx in protected_lows:
                candidates_raw.append((level, idx, 'protected_low'))
            for level, idx in order_blocks:
                candidates_raw.append((level, idx, 'order_block'))
        else:
            for level, idx in swing_highs:
                candidates_raw.append((level, idx, 'swing_high'))
            for level, idx in protected_highs:
                candidates_raw.append((level, idx, 'protected_high'))
            for level, idx in order_blocks:
                candidates_raw.append((level, idx, 'order_block'))

        # Filter by 15m swing if enabled
        if self.use_15m_filter and df_15m is not None:
            filtered_by_15m = []
            for level, idx, typ in candidates_raw:
                if bias == 'bullish':
                    if self._is_swing_low_15m(level, df_15m):
                        filtered_by_15m.append((level, idx, typ))
                else:
                    if self._is_swing_high_15m(level, df_15m):
                        filtered_by_15m.append((level, idx, typ))
            candidates_raw = filtered_by_15m

        # Deduplicate and merge close levels
        levels_dict = {}
        for level, idx, typ in candidates_raw:
            key = round(level / (current_price * self.merge_threshold_pct)) if self.merge_threshold_pct > 0 else level
            if key not in levels_dict or idx > levels_dict[key][1]:
                levels_dict[key] = (level, idx, typ)
        unique = list(levels_dict.values())

        # Filter by distance and direction
        filtered = []
        for level, idx, typ in unique:
            dist_pct = abs(level - current_price) / current_price
            if dist_pct > self.max_distance_pct:
                continue
            if bias == 'bullish' and level >= current_price:
                continue
            if bias == 'bearish' and level <= current_price:
                continue
            if dist_pct < self.min_distance_pct:
                continue
            filtered.append((level, idx, typ, dist_pct))

        if not filtered:
            return []

        max_idx = len(df_5m) - 1
        scored = []
        for level, idx, typ, dist_pct in filtered:
            recency = idx / max_idx
            distance_score = 1.0 - (dist_pct / self.max_distance_pct)
            type_boost = 1.0
            if typ == 'order_block':
                type_boost = 1.2
            elif typ == 'protected_low' or typ == 'protected_high':
                type_boost = 1.1
            score = (0.4 * recency) + (0.4 * distance_score) + (0.2 * type_boost)
            scored.append({
                'level': level,
                'type': typ,
                'score': score,
                'index': idx
            })

        scored.sort(key=lambda x: (-x['score'], abs(x['level'] - current_price)))
        return scored[:self.max_watchlist]