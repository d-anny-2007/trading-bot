import pandas as pd
import numpy as np
from typing import Dict

def detect_structure(df: pd.DataFrame) -> Dict[str, str]:
    if df is None or len(df) < 30:
        return {"bias": "unclear", "details": "Insufficient data"}

    highs = df["high"].values
    lows = df["low"].values

    recent_highs = highs[-20:]
    recent_lows = lows[-20:]

    hh_count = 0
    hl_count = 0
    lh_count = 0
    ll_count = 0

    last_5_highs = recent_highs[-5:]
    prev_5_highs = recent_highs[-10:-5]
    last_5_lows = recent_lows[-5:]
    prev_5_lows = recent_lows[-10:-5]

    if np.mean(last_5_highs) > np.mean(prev_5_highs):
        hh_count += 1
    if np.mean(last_5_lows) > np.mean(prev_5_lows):
        hl_count += 1
    if np.mean(last_5_highs) < np.mean(prev_5_highs):
        lh_count += 1
    if np.mean(last_5_lows) < np.mean(prev_5_lows):
        ll_count += 1

    if hh_count and hl_count and not (lh_count or ll_count):
        bias = "bullish"
    elif lh_count and ll_count and not (hh_count or hl_count):
        bias = "bearish"
    elif (hh_count and hl_count) and (lh_count or ll_count):
        bias = "mixed"
    else:
        bias = "unclear"

    details = f"HH:{hh_count} HL:{hl_count} LH:{lh_count} LL:{ll_count}"
    return {"bias": bias, "details": details}

def determine_overall_bias(btc_data: Dict[str, pd.DataFrame],
                           eth_data: Dict[str, pd.DataFrame],
                           xau_data: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, str]]:
    result = {}
    for symbol, data_dict in [("BTCUSD", btc_data), ("ETHUSD", eth_data), ("XAUUSD", xau_data)]:
        if not data_dict:
            result[symbol] = {"bias": "unclear", "details": "No data"}
            continue
        tf_bias = {}
        for tf_name, df in data_dict.items():
            tf_bias[tf_name] = detect_structure(df)
        primary = tf_bias.get("5m", {})
        context = tf_bias.get("15m", {})
        exec_bias = tf_bias.get("3m", {})

        if primary.get("bias") == "unclear" and context.get("bias") != "unclear":
            overall = context["bias"]
        else:
            overall = primary.get("bias", "unclear")

        result[symbol] = {"bias": overall, "details": f"5m:{primary.get('details','')} 15m:{context.get('details','')} 3m:{exec_bias.get('details','')}"}
    return result