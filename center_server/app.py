#!/usr/bin/env python3
"""
Center Server for Router Benchmark
Receives logs from benchmark clients and provides visualization
"""

from flask import Flask, request, jsonify, render_template
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)

# Data directory
DATA_DIR = Path('/app/data')
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / 'benchmark_data.jsonl'
CLIENTS_FILE = DATA_DIR / 'clients.json'

# In-memory client registry (last heartbeat times)
clients_registry = {}

def load_clients_registry():
    """Load clients registry from file"""
    global clients_registry
    if CLIENTS_FILE.exists():
        try:
            with open(CLIENTS_FILE, 'r') as f:
                clients_registry = json.load(f)
        except Exception as e:
            print(f"Error loading clients registry: {e}")
            clients_registry = {}
    else:
        clients_registry = {}

def save_clients_registry():
    """Save clients registry to file"""
    try:
        with open(CLIENTS_FILE, 'w') as f:
            json.dump(clients_registry, f, indent=2)
    except Exception as e:
        print(f"Error saving clients registry: {e}")

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
    - client_id: filter by specific client (optional, default: all clients)
    """
    try:
        limit = int(request.args.get('limit', 100))
        client_id_filter = request.args.get('client_id', None)

        if not LOG_FILE.exists():
            return jsonify({'data': []})

        # Read all logs
        logs = []
        with open(LOG_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))

        # Filter by client_id if specified
        if client_id_filter and client_id_filter != 'all':
            logs = [log for log in logs if log.get('client_id') == client_id_filter]

        # Return most recent logs
        recent_logs = logs[-limit:] if len(logs) > limit else logs

        return jsonify({'data': recent_logs, 'total': len(logs)})

    except Exception as e:
        print(f"Error getting data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get summary statistics
    Optional query params:
    - client_id: filter by specific client (optional, default: all clients)
    """
    try:
        client_id_filter = request.args.get('client_id', None)

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

        # Filter by client_id if specified
        if client_id_filter and client_id_filter != 'all':
            logs = [log for log in logs if log.get('client_id') == client_id_filter]

        if not logs:
            return jsonify({'stats': {}})

        latest = logs[-1]

        stats = {
            'total_records': len(logs),
            'latest_timestamp': latest.get('timestamp'),
            'client_id': latest.get('client_id'),
            'hostname': latest.get('hostname'),
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

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Receive heartbeat from clients
    Expected format: {client_id: "...", hostname: "...", ...}
    """
    try:
        data = request.get_json()

        if not data or 'client_id' not in data:
            return jsonify({'error': 'client_id is required'}), 400

        client_id = data['client_id']

        # Update client registry
        clients_registry[client_id] = {
            'client_id': client_id,
            'hostname': data.get('hostname', 'unknown'),
            'last_heartbeat': datetime.now().isoformat(),
            'router1_interface': data.get('router1_interface'),
            'router2_interface': data.get('router2_interface'),
        }

        # Save to disk periodically (every heartbeat to keep it simple)
        save_clients_registry()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Heartbeat from client: {client_id}")

        return jsonify({'status': 'success', 'message': 'Heartbeat received'}), 200

    except Exception as e:
        print(f"Error receiving heartbeat: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """
    Get list of active clients
    Query params:
    - timeout: seconds to consider client offline (default: 120)
    """
    try:
        timeout_seconds = int(request.args.get('timeout', 120))
        now = datetime.now()

        clients_list = []
        for client_id, client_info in clients_registry.items():
            last_heartbeat = datetime.fromisoformat(client_info['last_heartbeat'])
            time_since_heartbeat = (now - last_heartbeat).total_seconds()

            client_data = {
                'client_id': client_id,
                'hostname': client_info.get('hostname', 'unknown'),
                'last_heartbeat': client_info['last_heartbeat'],
                'seconds_since_heartbeat': int(time_since_heartbeat),
                'status': 'online' if time_since_heartbeat < timeout_seconds else 'offline',
                'router1_interface': client_info.get('router1_interface'),
                'router2_interface': client_info.get('router2_interface'),
            }
            clients_list.append(client_data)

        # Sort by last heartbeat (most recent first)
        clients_list.sort(key=lambda x: x['last_heartbeat'], reverse=True)

        return jsonify({
            'clients': clients_list,
            'total': len(clients_list),
            'online': sum(1 for c in clients_list if c['status'] == 'online'),
            'offline': sum(1 for c in clients_list if c['status'] == 'offline')
        })

    except Exception as e:
        print(f"Error getting clients: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("="*60)
    print("Router Benchmark Center Server")
    print("="*60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Log file: {LOG_FILE}")
    print(f"Clients file: {CLIENTS_FILE}")
    print("Starting server on 0.0.0.0:5000")
    print("="*60)

    # Load existing clients registry
    load_clients_registry()
    print(f"Loaded {len(clients_registry)} client(s) from registry")

    app.run(host='0.0.0.0', port=5000, debug=False)
