import pandas as pd
import numpy as np
from typing import Dict, Tuple
from volatility import calculate_atr

class TradePlanner:
    def __init__(self, config: dict):
        self.rr_targets = config.get("FIXED_RR_TARGETS", (1.5, 2.5, 3.5))
        self.be_trigger_ratio = config.get("BE_TRIGGER_RATIO", 0.5)
        self.min_rr_for_tp1 = config.get("MIN_RR_FOR_TP1", 1.5)
        self.min_risk_pct = config.get("MIN_RISK_PCT", 0.0)
        self.atr_multiplier = config.get("ATR_STOP_MULTIPLIER", 0.5)
        self.atr_period = config.get("VOLATILITY_ATR_PERIOD", 20)

    def get_stop_loss(self, entry: float, poi: float, direction: str,
                      confirmation_candle: pd.Series, atr: float) -> float:
        """
        Place stop beyond the POI plus an ATR‑based buffer.
        """
        if direction == 'bullish':
            # Stop below the POI by ATR * multiplier
            sl = poi - (atr * self.atr_multiplier)
            # Ensure SL is not above the confirmation candle low (if it's lower)
            if sl > confirmation_candle['low']:
                sl = confirmation_candle['low'] - (atr * self.atr_multiplier * 0.5)
            return sl
        else:
            sl = poi + (atr * self.atr_multiplier)
            if sl < confirmation_candle['high']:
                sl = confirmation_candle['high'] + (atr * self.atr_multiplier * 0.5)
            return sl

    def get_take_profits(self, entry: float, risk: float, direction: str) -> Tuple[float, float, float]:
        if direction == 'bullish':
            tp1 = entry + risk * self.rr_targets[0]
            tp2 = entry + risk * self.rr_targets[1]
            tp3 = entry + risk * self.rr_targets[2]
        else:
            tp1 = entry - risk * self.rr_targets[0]
            tp2 = entry - risk * self.rr_targets[1]
            tp3 = entry - risk * self.rr_targets[2]
        return tp1, tp2, tp3

    def build_plan(self, df: pd.DataFrame, touch_idx: int, poi: float, direction: str,
                   confirmation_idx: int, atr: float) -> Dict:
        """
        Build a trade plan using ATR‑based stops and fixed RR targets.
        """
        entry = df.iloc[confirmation_idx]['close']
        confirmation_candle = df.iloc[confirmation_idx]
        sl = self.get_stop_loss(entry, poi, direction, confirmation_candle, atr)
        risk = abs(entry - sl)
        risk_pct = risk / entry

        # Reject if risk is too small
        if risk_pct < self.min_risk_pct:
            return None

        tp1, tp2, tp3 = self.get_take_profits(entry, risk, direction)

        # Check RR for TP1
        rr = abs(tp1 - entry) / risk if risk > 0 else 0
        if rr < self.min_rr_for_tp1:
            return None

        # Break‑even level
        if direction == 'bullish':
            be = entry + (tp1 - entry) * self.be_trigger_ratio
        else:
            be = entry - (entry - tp1) * self.be_trigger_ratio

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