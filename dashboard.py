from flask import Flask, jsonify, render_template
from flask_cors import CORS
import threading
import logging
import shared_data
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/active')
def api_active():
    return jsonify(shared_data.active_trades)

@app.route('/api/closed')
def api_closed():
    # return last 50 closed trades
    return jsonify(shared_data.closed_trades[-50:])

@app.route('/api/signals')
def api_signals():
    return jsonify(shared_data.recent_signals[-20:])


def run_dashboard(host='0.0.0.0', port=None):
    port = int(os.environ.get("PORT", port or 5000))
    app.run(host=host, port=port, debug=False, use_reloader=False)

def start_dashboard():
    """Start dashboard in a background thread."""
    thread = threading.Thread(target=run_dashboard, daemon=True)
    thread.start()
    logging.info("Dashboard started on http://0.0.0.0:5000")