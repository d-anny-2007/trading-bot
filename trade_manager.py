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

    def add_trade(self, trade: Dict):
        """Add a new trade to active trades."""
        trade['trade_id'] = self._next_trade_id()
        trade['entry_time'] = datetime.now()
        trade['tp1_hit'] = False
        trade['tp2_hit'] = False
        trade['tp3_hit'] = False
        trade['be_moved'] = False
        trade['closed'] = False
        self.active_trades.append(trade)
        logging.info(f"Trade added: [{trade['trade_id']}] {trade['symbol']} {trade['direction']} at {trade['entry']:.2f}")

    def update(self, symbol: str, current_price: float, timestamp: datetime, telegram_sender=None) -> List[Dict]:
        """
        Check all active trades for the given symbol against current price.
        Returns list of events.
        """
        events = []
        for trade in list(self.active_trades):
            if trade['symbol'] != symbol:
                continue
            if trade.get('closed'):
                continue

            if trade['direction'] == 'bullish':
                # SL hit
                if current_price <= trade['sl']:
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['sl']
                    trade['result'] = 'SL'
                    trade['closed'] = True
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'SL', 'trade': trade})
                # TP3 hit
                elif current_price >= trade['tp3'] and not trade['tp3_hit']:
                    trade['tp3_hit'] = True
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['tp3']
                    trade['result'] = 'TP3'
                    trade['closed'] = True
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'TP3', 'trade': trade})
                # TP2 hit
                elif current_price >= trade['tp2'] and not trade['tp2_hit']:
                    trade['tp2_hit'] = True
                    events.append({'type': 'TP2', 'trade': trade})
                # TP1 hit
                elif current_price >= trade['tp1'] and not trade['tp1_hit']:
                    trade['tp1_hit'] = True
                    events.append({'type': 'TP1', 'trade': trade})
                    if not trade['be_moved']:
                        trade['sl'] = trade['entry']
                        trade['be_moved'] = True
                        events.append({'type': 'BE_MOVED', 'trade': trade})
            else:  # bearish
                if current_price >= trade['sl']:
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['sl']
                    trade['result'] = 'SL'
                    trade['closed'] = True
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'SL', 'trade': trade})
                elif current_price <= trade['tp3'] and not trade['tp3_hit']:
                    trade['tp3_hit'] = True
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['tp3']
                    trade['result'] = 'TP3'
                    trade['closed'] = True
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'TP3', 'trade': trade})
                elif current_price <= trade['tp2'] and not trade['tp2_hit']:
                    trade['tp2_hit'] = True
                    events.append({'type': 'TP2', 'trade': trade})
                elif current_price <= trade['tp1'] and not trade['tp1_hit']:
                    trade['tp1_hit'] = True
                    events.append({'type': 'TP1', 'trade': trade})
                    if not trade['be_moved']:
                        trade['sl'] = trade['entry']
                        trade['be_moved'] = True
                        events.append({'type': 'BE_MOVED', 'trade': trade})

        # Send updates via Telegram using formatted messages
        if telegram_sender:
            for event in events:
                # Use the new update method
                telegram_sender.send_update(event['type'], event['trade'])

        return events