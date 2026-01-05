#!/usr/bin/env python3
"""
Center Server for Router Benchmark
Receives logs from benchmark clients and provides visualization
Includes remote command execution with mutual authentication
Includes web shell for remote terminal access
"""

from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import wraps
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Import auth and commands modules
import auth
import commands
from shell_manager import shell_manager
from ai_diagnostics import get_troubleshooter, configure_troubleshooter

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'router-benchmark-secret-key')

# Initialize Socket.IO with gevent for WebSocket support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

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


# ============================================================================
# WebSocket Shell Endpoints
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    print(f"[WebSocket] Client connected: {request.sid}")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    print(f"[WebSocket] Client disconnected: {request.sid}")

    # Check if this was an admin with an active shell session
    session = shell_manager.get_session_by_admin(request.sid)
    if session:
        # Notify the client to close the shell
        client_sid = shell_manager.get_client_sid(session.client_id)
        if client_sid:
            socketio.emit('shell_close', {
                'session_id': session.session_id
            }, room=client_sid)
        shell_manager.close_session(session.session_id)


@socketio.on('shell_register_client')
def handle_shell_register_client(data):
    """Client registers for shell capability"""
    client_id = data.get('client_id')
    api_key = data.get('api_key')

    if not client_id or not api_key:
        emit('shell_error', {'error': 'client_id and api_key required'})
        return

    # Verify client authentication
    is_valid, error_msg = auth.authenticate_client_request(client_id, api_key)
    if not is_valid:
        emit('shell_error', {'error': error_msg})
        return

    # Register the client for shell
    shell_manager.register_client(client_id, request.sid)

    emit('shell_registered', {
        'status': 'success',
        'client_id': client_id
    })

    print(f"[WebSocket] Shell client registered: {client_id}")


@socketio.on('shell_unregister_client')
def handle_shell_unregister_client(data):
    """Client unregisters from shell capability"""
    client_id = data.get('client_id')
    if client_id:
        shell_manager.unregister_client(client_id)


@socketio.on('shell_list_clients')
def handle_shell_list_clients(data):
    """Admin requests list of shell-capable clients"""
    api_key = data.get('api_key')

    if not api_key:
        emit('shell_error', {'error': 'api_key required'})
        return

    # Verify admin authentication
    is_valid, error_msg = auth.authenticate_admin_request(api_key)
    if not is_valid:
        emit('shell_error', {'error': error_msg})
        return

    clients = shell_manager.get_connected_clients()
    emit('shell_clients', {'clients': clients})


@socketio.on('shell_start')
def handle_shell_start(data):
    """Admin requests to start a shell session with a client"""
    api_key = data.get('api_key')
    client_id = data.get('client_id')
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)

    if not api_key or not client_id:
        emit('shell_error', {'error': 'api_key and client_id required'})
        return

    # Verify admin authentication
    is_valid, error_msg = auth.authenticate_admin_request(api_key)
    if not is_valid:
        emit('shell_error', {'error': error_msg})
        return

    # Check if client is connected
    if not shell_manager.is_client_connected(client_id):
        emit('shell_error', {'error': f'Client {client_id} is not connected for shell'})
        return

    # Create session
    session = shell_manager.create_session(client_id, request.sid, rows, cols)
    if not session:
        emit('shell_error', {'error': 'Failed to create session. Client may have too many active sessions.'})
        return

    # Notify the client to start a shell
    client_sid = shell_manager.get_client_sid(client_id)
    if client_sid:
        socketio.emit('shell_open', {
            'session_id': session.session_id,
            'rows': rows,
            'cols': cols
        }, room=client_sid)

    # Notify admin that session is pending
    emit('shell_session_pending', {
        'session_id': session.session_id,
        'client_id': client_id
    })

    print(f"[WebSocket] Shell session requested: {session.session_id[:8]}... -> {client_id}")


@socketio.on('shell_ready')
def handle_shell_ready(data):
    """Client reports that shell is ready"""
    session_id = data.get('session_id')
    client_id = data.get('client_id')

    session = shell_manager.get_session(session_id)
    if not session:
        emit('shell_error', {'error': 'Invalid session'})
        return

    session.client_sid = request.sid
    session.status = 'connected'

    # Notify admin that shell is ready
    socketio.emit('shell_connected', {
        'session_id': session_id,
        'client_id': client_id
    }, room=session.admin_sid)

    print(f"[WebSocket] Shell session connected: {session_id[:8]}...")


@socketio.on('shell_input')
def handle_shell_input(data):
    """Admin sends input to the shell"""
    session_id = data.get('session_id')
    input_data = data.get('input', '')

    session = shell_manager.get_session(session_id)
    if not session or session.status != 'connected':
        emit('shell_error', {'error': 'Session not connected'})
        return

    # Verify this is the session owner
    if session.admin_sid != request.sid:
        emit('shell_error', {'error': 'Unauthorized'})
        return

    session.update_activity()

    # Forward input to client
    client_sid = shell_manager.get_client_sid(session.client_id)
    if client_sid:
        socketio.emit('shell_input', {
            'session_id': session_id,
            'input': input_data
        }, room=client_sid)


@socketio.on('shell_output')
def handle_shell_output(data):
    """Client sends shell output"""
    session_id = data.get('session_id')
    output_data = data.get('output', '')

    session = shell_manager.get_session(session_id)
    if not session:
        return

    session.update_activity()

    # Forward output to admin
    socketio.emit('shell_output', {
        'session_id': session_id,
        'output': output_data
    }, room=session.admin_sid)


@socketio.on('shell_resize')
def handle_shell_resize(data):
    """Admin resizes the terminal"""
    session_id = data.get('session_id')
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)

    session = shell_manager.get_session(session_id)
    if not session or session.admin_sid != request.sid:
        return

    session.rows = rows
    session.cols = cols
    session.update_activity()

    # Forward resize to client
    client_sid = shell_manager.get_client_sid(session.client_id)
    if client_sid:
        socketio.emit('shell_resize', {
            'session_id': session_id,
            'rows': rows,
            'cols': cols
        }, room=client_sid)


@socketio.on('shell_close')
def handle_shell_close(data):
    """Close a shell session"""
    session_id = data.get('session_id')

    session = shell_manager.get_session(session_id)
    if not session:
        return

    # Notify the other party
    if request.sid == session.admin_sid:
        # Admin closed, notify client
        client_sid = shell_manager.get_client_sid(session.client_id)
        if client_sid:
            socketio.emit('shell_close', {
                'session_id': session_id
            }, room=client_sid)
    else:
        # Client closed, notify admin
        socketio.emit('shell_closed', {
            'session_id': session_id,
            'reason': 'Client closed the session'
        }, room=session.admin_sid)

    shell_manager.close_session(session_id)
    print(f"[WebSocket] Shell session closed: {session_id[:8]}...")


@socketio.on('shell_client_exit')
def handle_shell_client_exit(data):
    """Client reports shell process exited"""
    session_id = data.get('session_id')
    exit_code = data.get('exit_code', 0)

    session = shell_manager.get_session(session_id)
    if not session:
        return

    # Notify admin
    socketio.emit('shell_closed', {
        'session_id': session_id,
        'reason': f'Shell exited with code {exit_code}'
    }, room=session.admin_sid)

    shell_manager.close_session(session_id)
    print(f"[WebSocket] Shell exited: {session_id[:8]}... (code={exit_code})")


# REST endpoint to check shell-capable clients
@app.route('/api/shell/clients', methods=['GET'])
@require_admin_auth
def get_shell_clients():
    """Get list of clients available for shell access"""
    try:
        clients = shell_manager.get_connected_clients()
        return jsonify({
            'clients': clients,
            'total': len(clients)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# AI Troubleshooting Endpoints
# ============================================================================

@app.route('/api/ai/config', methods=['GET'])
def get_ai_config():
    """Get AI troubleshooting configuration status"""
    try:
        troubleshooter = get_troubleshooter()
        return jsonify(troubleshooter.get_config_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/config', methods=['POST'])
@require_admin_auth
def set_ai_config():
    """
    Configure AI troubleshooting provider
    POST body: {
        "provider": "openai" or "anthropic",
        "api_key": "...",
        "model": "..." (optional)
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        provider = data.get('provider', 'openai')
        api_key = data.get('api_key')
        model = data.get('model')

        if not api_key:
            return jsonify({'error': 'api_key is required'}), 400

        troubleshooter = configure_troubleshooter(provider, api_key, model)

        return jsonify({
            'status': 'success',
            'config': troubleshooter.get_config_status()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/categories', methods=['GET'])
def get_ai_categories():
    """Get available diagnostic categories"""
    try:
        troubleshooter = get_troubleshooter()
        return jsonify({
            'categories': troubleshooter.get_diagnostic_categories()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/diagnose', methods=['POST'])
@require_admin_auth
def start_ai_diagnosis():
    """
    Start an AI diagnostic session for a client.
    This queues the necessary diagnostic commands and creates a session.

    POST body: {
        "client_id": "target-client",
        "categories": ["system", "disk", "network"],  # optional, defaults to all
        "question": "Optional specific question"  # optional
    }
    """
    try:
        data = request.get_json()
        if not data or 'client_id' not in data:
            return jsonify({'error': 'client_id is required'}), 400

        client_id = data['client_id']
        categories = data.get('categories', ['system', 'disk', 'network'])
        question = data.get('question')

        troubleshooter = get_troubleshooter()

        # Check if AI is configured
        if not troubleshooter.is_configured():
            return jsonify({
                'error': 'AI not configured. Configure via /api/ai/config or set environment variables.',
                'config': troubleshooter.get_config_status()
            }), 400

        # Create diagnostic session
        session = troubleshooter.create_session(client_id, categories)

        # Get commands needed for the categories
        required_commands = troubleshooter.get_commands_for_categories(categories)

        # Get admin info
        api_key = request.headers.get('X-Admin-API-Key')
        admin_secrets = auth.load_admin_secrets()
        admin_name = admin_secrets.get(api_key, {}).get('name', 'unknown')

        # Queue all diagnostic commands
        queued_commands = []
        for cmd_id in required_commands:
            try:
                cmd = commands.queue_command(client_id, cmd_id, {}, admin_name)
                if cmd:
                    queued_commands.append({
                        'command_id': cmd_id,
                        'command_uuid': cmd['command_uuid']
                    })
            except Exception as e:
                print(f"Failed to queue command {cmd_id}: {e}")

        session.status = 'collecting'

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI diagnosis started for: {client_id}")

        return jsonify({
            'status': 'success',
            'session_id': session.session_id,
            'client_id': client_id,
            'categories': categories,
            'commands_queued': queued_commands,
            'question': question,
            'message': 'Diagnostic commands queued. Poll /api/ai/diagnose/<session_id> for results.'
        }), 201

    except Exception as e:
        print(f"Error starting AI diagnosis: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/diagnose/<session_id>', methods=['GET'])
@require_admin_auth
def get_ai_diagnosis_status(session_id):
    """Get the status/results of a diagnostic session"""
    try:
        troubleshooter = get_troubleshooter()
        session = troubleshooter.get_session(session_id)

        if not session:
            return jsonify({'error': 'Session not found'}), 404

        return jsonify({
            'session_id': session.session_id,
            'client_id': session.client_id,
            'status': session.status,
            'categories': session.categories,
            'created_at': session.created_at,
            'data_collected': list(session.diagnostic_data.keys()),
            'diagnosis': session.diagnosis,
            'error': session.error
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/diagnose/<session_id>/data', methods=['POST'])
@require_admin_auth
def update_ai_diagnosis_data(session_id):
    """
    Update diagnostic session with command results.
    Called after command results are received.

    POST body: {
        "command_id": "system_info",
        "result": {
            "stdout": "...",
            "stderr": "...",
            "exit_code": 0
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        command_id = data.get('command_id')
        result = data.get('result', {})

        if not command_id:
            return jsonify({'error': 'command_id is required'}), 400

        troubleshooter = get_troubleshooter()
        success = troubleshooter.update_session_data(session_id, command_id, result)

        if not success:
            return jsonify({'error': 'Session not found'}), 404

        return jsonify({
            'status': 'success',
            'message': f'Data for {command_id} added to session'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/diagnose/<session_id>/analyze', methods=['POST'])
@require_admin_auth
def run_ai_analysis(session_id):
    """
    Run AI analysis on collected diagnostic data.

    POST body: {
        "question": "Optional specific question"  # optional
    }
    """
    try:
        data = request.get_json() or {}
        question = data.get('question')

        troubleshooter = get_troubleshooter()
        result = troubleshooter.analyze(session_id, question)

        if 'error' in result:
            return jsonify(result), 400

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI analysis completed for session: {session_id[:8]}...")

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/quick-diagnose', methods=['POST'])
@require_admin_auth
def quick_ai_diagnosis():
    """
    Quick one-shot diagnosis using existing command results.
    Collects latest results and runs AI analysis immediately.

    POST body: {
        "client_id": "target-client",
        "question": "Optional specific question"
    }
    """
    try:
        data = request.get_json()
        if not data or 'client_id' not in data:
            return jsonify({'error': 'client_id is required'}), 400

        client_id = data['client_id']
        question = data.get('question')

        troubleshooter = get_troubleshooter()

        if not troubleshooter.is_configured():
            return jsonify({
                'error': 'AI not configured. Configure via /api/ai/config or set environment variables.'
            }), 400

        # Get recent command results for this client
        recent_results = commands.get_command_results(client_id, limit=50)

        if not recent_results:
            return jsonify({
                'error': 'No recent command results found for this client. Run some diagnostic commands first.'
            }), 400

        # Build diagnostic data from recent results
        diagnostic_data = {}
        for result in recent_results:
            cmd_id = result.get('command_id')
            if cmd_id:
                diagnostic_data[cmd_id] = {
                    'stdout': result.get('stdout', ''),
                    'stderr': result.get('stderr', ''),
                    'exit_code': result.get('exit_code'),
                    'executed_at': result.get('executed_at')
                }

        # Add question to the diagnostic data if provided
        result = troubleshooter.quick_analyze(diagnostic_data, client_id)

        if question and result.get('status') == 'completed':
            # Re-run with the question
            result = troubleshooter.quick_analyze(diagnostic_data, client_id)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Quick AI diagnosis for: {client_id}")

        return jsonify(result)

    except Exception as e:
        print(f"Error in quick diagnosis: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("="*60)
    print("Router Benchmark Center Server")
    print("="*60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Log file: {LOG_FILE}")
    print(f"Clients file: {CLIENTS_FILE}")
    print("Starting server on 0.0.0.0:5000 (WebSocket enabled)")
    print("="*60)

    # Load existing clients registry
    load_clients_registry()
    print(f"Loaded {len(clients_registry)} client(s) from registry")

    # Run with Socket.IO (gevent)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
