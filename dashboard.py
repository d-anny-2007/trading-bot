from flask import Flask, jsonify, render_template
from flask_cors import CORS
import threading
import logging
import os
from datetime import datetime
import shared_data

app = Flask(__name__)
CORS(app)


def serialize_trade(trade):
    """Convert datetime objects to strings for JSON safety."""
    serialized = trade.copy()
    for key, value in serialized.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
    return serialized


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/active')
def api_active():
    return jsonify([serialize_trade(t) for t in shared_data.active_trades])


@app.route('/api/closed')
def api_closed():
    return jsonify([serialize_trade(t) for t in shared_data.closed_trades[-50:]])


@app.route('/api/signals')
def api_signals():
    return jsonify([
        {
            **s,
            "time": s["time"].isoformat() if isinstance(s.get("time"), datetime) else s.get("time")
        }
        for s in shared_data.recent_signals[-20:]
    ])


def run_dashboard():
    """Run Flask app using Railway-compatible PORT."""
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting dashboard on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def start_dashboard():
    """Start dashboard in background thread."""
    thread = threading.Thread(target=run_dashboard, daemon=True)
    thread.start()
    logging.info("Dashboard thread started")