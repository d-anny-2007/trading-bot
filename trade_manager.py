import logging
from typing import Dict, List
from datetime import datetime


class TradeManager:
    def __init__(self):
        self.active_trades: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self._next_id = 0

    def _next_trade_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @staticmethod
    def _is_bullish(direction: str) -> bool:
        d = str(direction or "").lower()
        return d in {"bullish", "buy", "long", "up"}

    @staticmethod
    def _symbol_code(symbol: str) -> str:
        raw = str(symbol or "").upper().replace("/", "").replace("-", "").replace("_", "")
        if raw.startswith("BTC"):
            return "BTC"
        if raw.startswith("ETH"):
            return "ETH"
        if raw.startswith("XAU"):
            return "XAU"
        if raw.startswith("XAG"):
            return "XAG"
        if raw:
            return raw[:4]
        return "TRD"

    def _build_trade_ref(self, trade: Dict) -> str:
        symbol_code = self._symbol_code(trade.get("symbol"))
        direction_code = "BULL" if self._is_bullish(trade.get("direction")) else "BEAR"
        entry_time = trade.get("entry_time")
        if isinstance(entry_time, datetime):
            stamp = entry_time.strftime("%Y%m%d-%H%M")
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
        trade_id = int(trade.get("trade_id", 0))
        return f"GS-{symbol_code}-{direction_code}-{stamp}-{trade_id:03d}"

    def add_trade(self, trade: Dict) -> Dict:
        """Add a new trade to active trades."""
        trade["symbol"] = str(trade.get("symbol", "")).upper()
        trade["direction"] = str(trade.get("direction", "")).lower()
        trade["trade_id"] = self._next_trade_id()
        trade["entry_time"] = datetime.now()
        trade["tp1_hit"] = False
        trade["tp2_hit"] = False
        trade["tp3_hit"] = False
        trade["be_moved"] = False
        trade["closed"] = False
        trade["trade_ref"] = self._build_trade_ref(trade)
        trade["trade_label"] = f"{trade['symbol']} • {trade['direction'].upper()} • {trade['entry_time'].strftime('%Y-%m-%d %H:%M')}"
        self.active_trades.append(trade)
        logging.info(
            f"Trade added: [{trade['trade_id']}] {trade['trade_ref']} "
            f"{trade['symbol']} {trade['direction']} at {trade['entry']:.2f}"
        )
        return trade

    def _close_trade(self, trade: Dict, timestamp: datetime, exit_price: float, result: str):
        trade["exit_time"] = timestamp
        trade["exit_price"] = exit_price
        trade["result"] = result
        trade["closed"] = True
        if trade in self.active_trades:
            self.active_trades.remove(trade)
        self.closed_trades.append(trade)

    def update(self, symbol: str, current_price: float, timestamp: datetime, telegram_sender=None) -> List[Dict]:
        """
        Check all active trades for the given symbol against current price.
        Returns list of events.
        """
        events = []

        for trade in list(self.active_trades):
            if trade["symbol"] != symbol:
                continue
            if trade.get("closed"):
                continue

            bullish = trade["direction"] == "bullish"

            if bullish:
                if current_price <= trade["sl"]:
                    self._close_trade(trade, timestamp, trade["sl"], "SL")
                    events.append({"type": "SL", "trade": trade})

                elif current_price >= trade["tp3"]:
                    trade["tp1_hit"] = True
                    trade["tp2_hit"] = True
                    trade["tp3_hit"] = True
                    if not trade["be_moved"]:
                        trade["sl"] = trade["entry"]
                        trade["be_moved"] = True
                    self._close_trade(trade, timestamp, trade["tp3"], "TP3")
                    events.append({"type": "TP3", "trade": trade})

                elif current_price >= trade["tp2"] and not trade["tp2_hit"]:
                    if not trade["tp1_hit"]:
                        trade["tp1_hit"] = True
                        if not trade["be_moved"]:
                            trade["sl"] = trade["entry"]
                            trade["be_moved"] = True
                    trade["tp2_hit"] = True
                    events.append({"type": "TP2", "trade": trade})

                elif current_price >= trade["tp1"] and not trade["tp1_hit"]:
                    trade["tp1_hit"] = True
                    if not trade["be_moved"]:
                        trade["sl"] = trade["entry"]
                        trade["be_moved"] = True
                    events.append({"type": "TP1", "trade": trade})

            else:
                if current_price >= trade["sl"]:
                    self._close_trade(trade, timestamp, trade["sl"], "SL")
                    events.append({"type": "SL", "trade": trade})

                elif current_price <= trade["tp3"]:
                    trade["tp1_hit"] = True
                    trade["tp2_hit"] = True
                    trade["tp3_hit"] = True
                    if not trade["be_moved"]:
                        trade["sl"] = trade["entry"]
                        trade["be_moved"] = True
                    self._close_trade(trade, timestamp, trade["tp3"], "TP3")
                    events.append({"type": "TP3", "trade": trade})

                elif current_price <= trade["tp2"] and not trade["tp2_hit"]:
                    if not trade["tp1_hit"]:
                        trade["tp1_hit"] = True
                        if not trade["be_moved"]:
                            trade["sl"] = trade["entry"]
                            trade["be_moved"] = True
                    trade["tp2_hit"] = True
                    events.append({"type": "TP2", "trade": trade})

                elif current_price <= trade["tp1"] and not trade["tp1_hit"]:
                    trade["tp1_hit"] = True
                    if not trade["be_moved"]:
                        trade["sl"] = trade["entry"]
                        trade["be_moved"] = True
                    events.append({"type": "TP1", "trade": trade})

        if telegram_sender:
            for event in events:
                telegram_sender.send_update(event["type"], event["trade"])

        return events