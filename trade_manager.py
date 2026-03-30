import logging
from typing import Dict, List
from datetime import datetime

class TradeManager:
    def __init__(self):
        self.active_trades: List[Dict] = []
        self.closed_trades: List[Dict] = []

    def add_trade(self, trade: Dict):
        """Add a new trade to active trades."""
        trade['entry_time'] = datetime.now()
        # Initialize hit flags
        trade['tp1_hit'] = False
        trade['tp2_hit'] = False
        trade['tp3_hit'] = False
        trade['be_moved'] = False
        self.active_trades.append(trade)
        logging.info(f"Trade added: {trade['symbol']} {trade['direction']} at {trade['entry']:.2f}")

    def update(self, symbol: str, current_price: float, timestamp: datetime, telegram_sender=None) -> List[Dict]:
        """
        Check all active trades for the given symbol against current price.
        Returns list of events (e.g., hit SL, TP).
        """
        events = []
        for trade in list(self.active_trades):
            if trade['symbol'] != symbol:
                continue

            if trade['direction'] == 'bullish':
                # Check stop loss
                if current_price <= trade['sl']:
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['sl']
                    trade['result'] = 'SL'
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'SL', 'trade': trade})
                # Check take profits in order
                elif current_price >= trade['tp1'] and not trade['tp1_hit']:
                    trade['tp1_hit'] = True
                    events.append({'type': 'TP1', 'trade': trade})
                    # Move SL to BE if not already moved
                    if not trade['be_moved']:
                        trade['sl'] = trade['entry']  # entry price
                        trade['be_moved'] = True
                        events.append({'type': 'BE_MOVED', 'trade': trade})
                elif current_price >= trade['tp2'] and not trade['tp2_hit']:
                    trade['tp2_hit'] = True
                    events.append({'type': 'TP2', 'trade': trade})
                elif current_price >= trade['tp3'] and not trade['tp3_hit']:
                    trade['tp3_hit'] = True
                    events.append({'type': 'TP3', 'trade': trade})
            else:  # bearish
                if current_price >= trade['sl']:
                    trade['exit_time'] = timestamp
                    trade['exit_price'] = trade['sl']
                    trade['result'] = 'SL'
                    self.active_trades.remove(trade)
                    self.closed_trades.append(trade)
                    events.append({'type': 'SL', 'trade': trade})
                elif current_price <= trade['tp1'] and not trade['tp1_hit']:
                    trade['tp1_hit'] = True
                    events.append({'type': 'TP1', 'trade': trade})
                    if not trade['be_moved']:
                        trade['sl'] = trade['entry']
                        trade['be_moved'] = True
                        events.append({'type': 'BE_MOVED', 'trade': trade})
                elif current_price <= trade['tp2'] and not trade['tp2_hit']:
                    trade['tp2_hit'] = True
                    events.append({'type': 'TP2', 'trade': trade})
                elif current_price <= trade['tp3'] and not trade['tp3_hit']:
                    trade['tp3_hit'] = True
                    events.append({'type': 'TP3', 'trade': trade})

        # Send Telegram updates for events
        if telegram_sender:
            for event in events:
                self._send_event_notification(event, telegram_sender)
        return events

    def _send_event_notification(self, event: Dict, telegram):
        trade = event['trade']
        if event['type'] == 'SL':
            text = f"❌ {trade['symbol']} {trade['direction'].upper()} hit SL at {trade['sl']:.2f}"
        elif event['type'] == 'TP1':
            text = f"✅ {trade['symbol']} {trade['direction'].upper()} hit TP1 at {trade['tp1']:.2f}. SL moved to BE."
        elif event['type'] == 'TP2':
            text = f"✅ {trade['symbol']} {trade['direction'].upper()} hit TP2 at {trade['tp2']:.2f}"
        elif event['type'] == 'TP3':
            text = f"✅ {trade['symbol']} {trade['direction'].upper()} hit TP3 at {trade['tp3']:.2f} – trade closed."
        elif event['type'] == 'BE_MOVED':
            text = f"🔒 {trade['symbol']} {trade['direction'].upper()} SL moved to break-even at {trade['sl']:.2f}."
        else:
            return
        telegram.send_message(text)