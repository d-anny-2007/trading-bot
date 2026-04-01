import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

class POIDiscovery:
    def __init__(self, config: dict):
        self.max_watchlist = config.get("MAX_WATCHLIST_SIZE", 3)
        self.max_distance_pct = config.get("MAX_POI_DISTANCE_PCT", 0.02)
        self.min_distance_pct = config.get("MIN_POI_DISTANCE_PCT", 0.004)
        self.merge_threshold_pct = config.get("MERGE_THRESHOLD_PCT", 0.0005)
        self.swing_strength_pct = config.get("SWING_STRENGTH_PCT", 0.003)
        self.use_15m_filter = config.get("USE_15M_POI_FILTER", False)
        self.min_displacement_pct = config.get("MIN_DISPLACEMENT_PCT", 0.005)   # 0.5%
        self.max_tap_count = config.get("MAX_TAP_COUNT", 2)
        self.use_htf_swing = config.get("USE_HTF_SWING_FILTER", True)

        # Track tap history and formation indices for levels
        self.tap_history = defaultdict(list)      # level -> list of tap indices
        self.formation_index = {}                  # level -> index of first detection

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
            if candle['high'] - max(candle['open'], candle['close']) > body * 1.5:
                if self._is_swing_high(df['high'].values, i, window):
                    protected_highs.append((candle['high'], i))
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
            if move_pct < 0.003:      # require at least 0.3% move
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

    def _mitigation_count(self, level: float, current_idx: int, lookback: int = 50) -> int:
        """Count how many times price has tapped this level in the recent past."""
        taps = self.tap_history.get(level, [])
        return sum(1 for idx in taps if current_idx - idx <= lookback)

    def _has_displacement(self, df: pd.DataFrame, formation_idx: int, level: float, threshold_pct: float = 0.005) -> bool:
        """
        Check if price moved away from the level by at least threshold_pct after formation.
        """
        if formation_idx is None:
            return False
        after_df = df.iloc[formation_idx+1:]
        if len(after_df) < 5:
            return False
        max_high = after_df['high'].max()
        min_low = after_df['low'].min()
        # For bullish, we want price to have moved up above level; for bearish, down below.
        # We check both directions.
        upward = (max_high - level) / level > threshold_pct
        downward = (level - min_low) / level > threshold_pct
        return upward or downward

    def _is_strong_structure(self, df_5m: pd.DataFrame, idx: int, level: float, bias: str,
                             df_15m: Optional[pd.DataFrame]) -> bool:
        """Determine if a level qualifies as a strong POI."""
        # 1. Check HTF confluence if required
        if self.use_htf_swing and df_15m is not None:
            if bias == 'bullish' and not self._is_swing_low_15m(level, df_15m):
                return False
            if bias == 'bearish' and not self._is_swing_high_15m(level, df_15m):
                return False
        # 2. Check displacement: price must have moved strongly away after formation
        formation_idx = self.formation_index.get(level)
        if formation_idx is None:
            # First time seeing this level – we don't have displacement data yet; we'll track it.
            self.formation_index[level] = idx
            return False
        if not self._has_displacement(df_5m, formation_idx, level, self.min_displacement_pct):
            return False
        # 3. Mitigation count: if tapped too many times recently, reject
        if self._mitigation_count(level, idx) >= self.max_tap_count:
            return False
        return True

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

        # Merge close levels
        levels_dict = {}
        for level, idx, typ in candidates_raw:
            key = round(level / (current_price * self.merge_threshold_pct)) if self.merge_threshold_pct > 0 else level
            if key not in levels_dict or idx > levels_dict[key][1]:
                levels_dict[key] = (level, idx, typ)
        unique = list(levels_dict.values())

        # Apply structural filters
        strong_candidates = []
        for level, idx, typ in unique:
            # Basic distance filter
            dist_pct = abs(level - current_price) / current_price
            if dist_pct > self.max_distance_pct:
                continue
            if bias == 'bullish' and level >= current_price:
                continue
            if bias == 'bearish' and level <= current_price:
                continue
            if dist_pct < self.min_distance_pct:
                continue

            # Now check structural strength
            if self._is_strong_structure(df_5m, idx, level, bias, df_15m):
                strong_candidates.append((level, idx, typ, dist_pct))
            else:
                continue

        if not strong_candidates:
            return []

        # Sort by distance (nearest first) and take up to max_watchlist
        strong_candidates.sort(key=lambda x: (abs(x[0] - current_price), x[1]))
        top_candidates = strong_candidates[:self.max_watchlist]

        # Build result list
        result = []
        for level, idx, typ, _ in top_candidates:
            result.append({
                'level': level,
                'type': typ,
                'score': 1.0,   # dummy, keep for compatibility
                'index': idx
            })
        return result