import pandas as pd
import numpy as np
from typing import Dict, Tuple

class TradePlanner:
    def __init__(self, config: dict):
        self.rr_targets = config.get("RR_TARGETS", (1.0, 2.0, 3.0))
        self.be_trigger_ratio = config.get("BE_TRIGGER_RATIO", 0.5)
        self.min_rr_for_tp1 = config.get("MIN_RR_FOR_TP1", 1.0)

    def get_stop_loss(self, df: pd.DataFrame, touch_idx: int, poi: float, direction: str,
                      confirmation_idx: int) -> float:
        conf_candle = df.iloc[confirmation_idx]
        if direction == 'bullish':
            sl = min(poi, conf_candle['low'])
            buffer = sl * 0.0005
            return sl - buffer
        else:
            sl = max(poi, conf_candle['high'])
            buffer = sl * 0.0005
            return sl + buffer

    def get_take_profits(self, entry: float, sl: float, direction: str,
                         df: pd.DataFrame, conf_idx: int) -> Tuple[float, float, float]:
        risk = abs(entry - sl)
        if direction == 'bullish':
            future_highs = df['high'].iloc[conf_idx+1:].values
            next_swing = future_highs[0] if len(future_highs) else entry + risk * self.rr_targets[0]
            tp1 = max(next_swing, entry + risk * self.rr_targets[0])
            tp2 = entry + risk * self.rr_targets[1]
            tp3 = entry + risk * self.rr_targets[2]
        else:
            future_lows = df['low'].iloc[conf_idx+1:].values
            next_swing = future_lows[0] if len(future_lows) else entry - risk * self.rr_targets[0]
            tp1 = min(next_swing, entry - risk * self.rr_targets[0])
            tp2 = entry - risk * self.rr_targets[1]
            tp3 = entry - risk * self.rr_targets[2]
        return tp1, tp2, tp3

    def get_break_even_level(self, entry: float, sl: float, direction: str,
                             tp1: float) -> float:
        if direction == 'bullish':
            be_target = entry + (tp1 - entry) * self.be_trigger_ratio
        else:
            be_target = entry - (entry - tp1) * self.be_trigger_ratio
        return be_target

    def build_plan(self, df: pd.DataFrame, touch_idx: int, poi: float, direction: str,
                   confirmation_idx: int) -> Dict:
        entry = df.iloc[confirmation_idx]['close']
        sl = self.get_stop_loss(df, touch_idx, poi, direction, confirmation_idx)
        tp1, tp2, tp3 = self.get_take_profits(entry, sl, direction, df, confirmation_idx)
        risk = abs(entry - sl)
        reward = abs(tp1 - entry) if direction == 'bullish' else abs(entry - tp1)
        rr = reward / risk if risk > 0 else 0

        # Skip if RR is below minimum required
        if rr < self.min_rr_for_tp1:
            return None

        be = self.get_break_even_level(entry, sl, direction, tp1)
        return {
            'entry': entry,
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'be': be,
            'rr': rr,
            'confirmation_pattern': confirmation_idx
        }