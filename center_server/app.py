#!/usr/bin/env python3
"""
Center Server for Router Benchmark
Receives logs from benchmark clients and provides visualization
Includes remote command execution with mutual authentication
"""

from flask import Flask, request, jsonify, render_template
from functools import wraps
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Import auth and commands modules
import auth
import commands

app = Flask(__name__)

# Data directory (configurable via environment variable for testing)
DATA_DIR = Path(os.environ.get('DATA_DIR', '/app/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
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


# ============================================================================
# Authentication Decorators
# ============================================================================

def require_admin_auth(f):
    """Decorator to require admin API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-Admin-API-Key')
        is_valid, error_msg = auth.authenticate_admin_request(api_key)

        if not is_valid:
            return jsonify({'error': error_msg}), 401

        return f(*args, **kwargs)
    return decorated_function


def require_client_auth(f):
    """Decorator to require client API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = request.headers.get('X-Client-ID')
        api_key = request.headers.get('X-Client-API-Key')

        if not client_id:
            return jsonify({'error': 'Missing X-Client-ID header'}), 401

        is_valid, error_msg = auth.authenticate_client_request(client_id, api_key)

        if not is_valid:
            return jsonify({'error': error_msg}), 401

        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# Admin Management Endpoints
# ============================================================================

@app.route('/api/admin/init', methods=['POST'])
def init_admin():
    """
    Initialize the first admin account (only works if no admins exist)
    POST body: {"admin_name": "..."}
    Returns: {"api_key": "..."}
    """
    try:
        existing_admins = auth.load_admin_secrets()
        if existing_admins:
            return jsonify({'error': 'Admin already initialized. Use existing admin key to create more.'}), 403

        data = request.get_json()
        if not data or 'admin_name' not in data:
            return jsonify({'error': 'admin_name is required'}), 400

        admin_name = data['admin_name']
        api_key = auth.create_admin_key(admin_name)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Admin initialized: {admin_name}")

        return jsonify({
            'status': 'success',
            'message': 'Admin account created. SAVE THIS API KEY - it cannot be retrieved later!',
            'api_key': api_key,
            'admin_name': admin_name
        }), 201

    except Exception as e:
        print(f"Error initializing admin: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/create', methods=['POST'])
@require_admin_auth
def create_admin():
    """
    Create a new admin account (requires existing admin auth)
    POST body: {"admin_name": "..."}
    """
    try:
        data = request.get_json()
        if not data or 'admin_name' not in data:
            return jsonify({'error': 'admin_name is required'}), 400

        admin_name = data['admin_name']
        api_key = auth.create_admin_key(admin_name)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New admin created: {admin_name}")

        return jsonify({
            'status': 'success',
            'message': 'Admin account created. SAVE THIS API KEY!',
            'api_key': api_key,
            'admin_name': admin_name
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Client Registration Endpoints
# ============================================================================

@app.route('/api/clients/register', methods=['POST'])
@require_admin_auth
def register_client():
    """
    Register a new client (requires admin auth)
    POST body: {"client_id": "..."}
    Returns the client's secret key for configuration
    """
    try:
        data = request.get_json()
        if not data or 'client_id' not in data:
            return jsonify({'error': 'client_id is required'}), 400

        client_id = data['client_id']

        try:
            secret_key = auth.register_client(client_id)
        except ValueError as e:
            return jsonify({'error': str(e)}), 409

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Client registered: {client_id}")

        return jsonify({
            'status': 'success',
            'message': 'Client registered. SAVE THIS SECRET KEY - it cannot be retrieved later!',
            'client_id': client_id,
            'secret_key': secret_key
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/registered', methods=['GET'])
@require_admin_auth
def list_registered_clients():
    """List all registered clients (requires admin auth)"""
    try:
        clients = auth.list_clients()
        return jsonify({
            'clients': clients,
            'total': len(clients)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clients/<client_id>/revoke', methods=['POST'])
@require_admin_auth
def revoke_client(client_id):
    """Revoke a client's access (requires admin auth)"""
    try:
        success = auth.revoke_client(client_id)
        if success:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Client revoked: {client_id}")
            return jsonify({'status': 'success', 'message': f'Client {client_id} revoked'})
        else:
            return jsonify({'error': 'Client not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Command Whitelist Endpoints
# ============================================================================

@app.route('/api/commands/whitelist', methods=['GET'])
def get_command_whitelist():
    """Get the list of available whitelisted commands"""
    try:
        whitelist = commands.list_whitelisted_commands()
        return jsonify({
            'commands': whitelist,
            'total': len(whitelist)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Command Execution Endpoints (Admin -> Server)
# ============================================================================

@app.route('/api/commands/send', methods=['POST'])
@require_admin_auth
def send_command():
    """
    Queue a command for a client (requires admin auth)
    POST body: {
        "client_id": "target-client",
        "command_id": "system_info",
        "params": {}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        required_fields = ['client_id', 'command_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        client_id = data['client_id']
        command_id = data['command_id']
        params = data.get('params', {})

        # Get admin info from API key
        api_key = request.headers.get('X-Admin-API-Key')
        admin_secrets = auth.load_admin_secrets()
        admin_name = admin_secrets.get(api_key, {}).get('name', 'unknown')

        try:
            signed_command = commands.queue_command(client_id, command_id, params, admin_name)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        if not signed_command:
            return jsonify({'error': 'Failed to queue command'}), 500

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Command queued: {command_id} -> {client_id}")

        return jsonify({
            'status': 'success',
            'message': 'Command queued',
            'command_uuid': signed_command['command_uuid'],
            'client_id': client_id,
            'command_id': command_id
        }), 201

    except Exception as e:
        print(f"Error sending command: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/commands/pending/<client_id>', methods=['GET'])
@require_admin_auth
def get_pending_commands_admin(client_id):
    """Get pending commands for a client (admin view)"""
    try:
        pending = commands.get_pending_commands(client_id)
        return jsonify({
            'client_id': client_id,
            'pending_commands': pending,
            'count': len(pending)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/commands/pending/<client_id>/clear', methods=['POST'])
@require_admin_auth
def clear_pending_commands(client_id):
    """Clear all pending commands for a client (requires admin auth)"""
    try:
        count = commands.clear_pending_commands(client_id)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cleared {count} pending commands for: {client_id}")
        return jsonify({
            'status': 'success',
            'message': f'Cleared {count} pending commands',
            'client_id': client_id,
            'cleared_count': count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Command Polling Endpoints (Client -> Server)
# ============================================================================

@app.route('/api/commands/poll', methods=['GET'])
@require_client_auth
def poll_commands():
    """
    Client polls for pending commands
    Returns the next pending command (signed) or empty if none
    """
    try:
        client_id = request.headers.get('X-Client-ID')
        command = commands.pop_pending_command(client_id)

        if command:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Command delivered to: {client_id}")
            return jsonify({
                'has_command': True,
                'command': command
            })
        else:
            return jsonify({
                'has_command': False,
                'command': None
            })

    except Exception as e:
        print(f"Error polling commands: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/commands/result', methods=['POST'])
@require_client_auth
def submit_command_result():
    """
    Client submits command execution result
    POST body: {
        "command_uuid": "...",
        "command_id": "...",
        "exit_code": 0,
        "stdout": "...",
        "stderr": "...",
        "executed_at": "...",
        "duration_seconds": 1.5
    }
    """
    try:
        client_id = request.headers.get('X-Client-ID')
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        if 'command_uuid' not in data:
            return jsonify({'error': 'command_uuid is required'}), 400

        # Add client_id and status
        data['client_id'] = client_id
        data['status'] = 'success' if data.get('exit_code') == 0 else 'failed'

        commands.store_command_result(data)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Command result from: {client_id} (exit={data.get('exit_code')})")

        return jsonify({
            'status': 'success',
            'message': 'Result received'
        })

    except Exception as e:
        print(f"Error receiving command result: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Command Results Endpoints (Admin)
# ============================================================================

@app.route('/api/commands/results', methods=['GET'])
@require_admin_auth
def get_command_results():
    """
    Get command execution results
    Query params:
    - client_id: filter by client (optional)
    - limit: max results (default: 100)
    """
    try:
        client_id = request.args.get('client_id')
        limit = int(request.args.get('limit', 100))

        results = commands.get_command_results(client_id, limit)

        return jsonify({
            'results': results,
            'total': len(results)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/commands/results/<command_uuid>', methods=['GET'])
@require_admin_auth
def get_command_result_by_id(command_uuid):
    """Get a specific command result by UUID"""
    try:
        result = commands.get_result_by_uuid(command_uuid)

        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Result not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/commands/audit', methods=['GET'])
@require_admin_auth
def get_audit_log():
    """
    Get command audit log
    Query params:
    - limit: max entries (default: 100)
    """
    try:
        limit = int(request.args.get('limit', 100))
        entries = commands.get_audit_log(limit)

        return jsonify({
            'entries': entries,
            'total': len(entries)
        })

    except Exception as e:
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
