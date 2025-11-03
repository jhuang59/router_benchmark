#!/usr/bin/env python3
"""
Center Server for Router Benchmark
Receives logs from benchmark clients and provides visualization
"""

from flask import Flask, request, jsonify, render_template
import json
import os
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

# Data directory
DATA_DIR = Path('/app/data')
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / 'benchmark_data.jsonl'

@app.route('/')
def index():
    """Serve the visualization dashboard"""
    return render_template('index.html')

@app.route('/api/logs', methods=['POST'])
def receive_logs():
    """
    Receive benchmark logs from clients
    Expected format: {timestamp, router1: {...}, router2: {...}}
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Add server reception timestamp
        data['server_received_at'] = datetime.now().isoformat()

        # Append to log file
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(data) + '\n')

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Received log from client")

        return jsonify({'status': 'success', 'message': 'Log received'}), 200

    except Exception as e:
        print(f"Error receiving log: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    """
    Get benchmark data for visualization
    Optional query params:
    - limit: number of recent records (default: 100)
    - hours: filter data from last N hours
    """
    try:
        limit = int(request.args.get('limit', 100))

        if not LOG_FILE.exists():
            return jsonify({'data': []})

        # Read all logs
        logs = []
        with open(LOG_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))

        # Return most recent logs
        recent_logs = logs[-limit:] if len(logs) > limit else logs

        return jsonify({'data': recent_logs, 'total': len(logs)})

    except Exception as e:
        print(f"Error getting data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get summary statistics"""
    try:
        if not LOG_FILE.exists():
            return jsonify({'stats': {}})

        # Read recent logs for stats
        logs = []
        with open(LOG_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))

        if not logs:
            return jsonify({'stats': {}})

        latest = logs[-1]

        stats = {
            'total_records': len(logs),
            'latest_timestamp': latest.get('timestamp'),
            'router1_latest_loss': latest.get('router1', {}).get('packet_loss_pct'),
            'router2_latest_loss': latest.get('router2', {}).get('packet_loss_pct'),
            'router1_latest_avg_ms': latest.get('router1', {}).get('avg_ms'),
            'router2_latest_avg_ms': latest.get('router2', {}).get('avg_ms'),
        }

        return jsonify({'stats': stats})

    except Exception as e:
        print(f"Error getting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    print("="*60)
    print("Router Benchmark Center Server")
    print("="*60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Log file: {LOG_FILE}")
    print("Starting server on 0.0.0.0:5000")
    print("="*60)

    app.run(host='0.0.0.0', port=5000, debug=False)
