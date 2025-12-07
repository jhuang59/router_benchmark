#!/usr/bin/env python3
"""
Command Management for Remote Command Execution
Handles command whitelist, queuing, and result storage
"""

import json
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import os

from auth import sign_command, load_client_secrets

# Configuration
DATA_DIR = Path(os.environ.get('DATA_DIR', '/app/data'))
WHITELIST_FILE = Path(__file__).parent / 'command_whitelist.json'
PENDING_COMMANDS_FILE = DATA_DIR / 'pending_commands.json'
COMMAND_RESULTS_FILE = DATA_DIR / 'command_results.jsonl'
COMMAND_AUDIT_LOG = DATA_DIR / 'command_audit.jsonl'

# Security limits
MAX_OUTPUT_SIZE = 65536  # 64KB max output
COMMAND_TIMEOUT_SECONDS = 60  # Default timeout


# ============================================================================
# Command Whitelist Management
# ============================================================================

def load_whitelist() -> dict:
    """Load the command whitelist from file"""
    if WHITELIST_FILE.exists():
        try:
            with open(WHITELIST_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading command whitelist: {e}")
            return {}
    return {}


def get_whitelisted_command(command_id: str) -> Optional[dict]:
    """Get a whitelisted command by its ID"""
    whitelist = load_whitelist()
    return whitelist.get('commands', {}).get(command_id)


def list_whitelisted_commands() -> List[dict]:
    """List all whitelisted commands"""
    whitelist = load_whitelist()
    commands = []

    for cmd_id, cmd_info in whitelist.get('commands', {}).items():
        commands.append({
            'id': cmd_id,
            'description': cmd_info.get('description', ''),
            'category': cmd_info.get('category', 'general'),
            'params': cmd_info.get('params', []),
            'timeout': cmd_info.get('timeout', COMMAND_TIMEOUT_SECONDS)
        })

    return commands


def validate_command_params(command_id: str, params: dict) -> tuple:
    """
    Validate parameters for a whitelisted command
    Returns (is_valid, error_message, sanitized_params)
    """
    cmd_info = get_whitelisted_command(command_id)
    if not cmd_info:
        return False, f"Command '{command_id}' not in whitelist", {}

    required_params = cmd_info.get('params', [])
    param_validators = cmd_info.get('param_validators', {})
    sanitized = {}

    # Check all required params are provided
    for param in required_params:
        if param not in params:
            return False, f"Missing required parameter: {param}", {}

        value = params[param]

        # Validate parameter format if validator is specified
        if param in param_validators:
            validator = param_validators[param]
            if not validate_param_value(value, validator):
                return False, f"Invalid value for parameter '{param}': {value}", {}

        # Basic sanitization - no shell metacharacters
        sanitized_value = sanitize_param_value(value)
        if sanitized_value is None:
            return False, f"Unsafe characters in parameter '{param}'", {}

        sanitized[param] = sanitized_value

    return True, "Valid", sanitized


def validate_param_value(value: str, validator: dict) -> bool:
    """Validate a parameter value against a validator spec"""
    validator_type = validator.get('type', 'string')

    if validator_type == 'ip':
        # Validate IPv4 address
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, value):
            return False
        # Check each octet is valid
        octets = value.split('.')
        for octet in octets:
            if int(octet) > 255:
                return False
        return True

    elif validator_type == 'hostname':
        # Validate hostname (alphanumeric, hyphens, dots)
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$'
        return bool(re.match(pattern, value)) and len(value) <= 255

    elif validator_type == 'integer':
        try:
            int_val = int(value)
            min_val = validator.get('min', float('-inf'))
            max_val = validator.get('max', float('inf'))
            return min_val <= int_val <= max_val
        except ValueError:
            return False

    elif validator_type == 'choice':
        choices = validator.get('choices', [])
        return value in choices

    elif validator_type == 'path':
        # Only allow safe paths (no .., no absolute paths starting with /)
        if '..' in value or value.startswith('/'):
            return False
        pattern = r'^[a-zA-Z0-9_\-\.\/]+$'
        return bool(re.match(pattern, value))

    return True  # Default: accept if no validator type specified


def sanitize_param_value(value: str) -> Optional[str]:
    """
    Sanitize a parameter value to prevent command injection
    Returns None if value contains unsafe characters
    """
    # Reject shell metacharacters
    dangerous_chars = ['`', '$', '|', ';', '&', '>', '<', '\n', '\r', '\\']
    for char in dangerous_chars:
        if char in value:
            return None

    # Limit length
    if len(value) > 256:
        return None

    return value


def build_command_string(command_id: str, params: dict) -> Optional[str]:
    """
    Build the actual command string from template and parameters
    Returns None if command not found or params invalid
    """
    cmd_info = get_whitelisted_command(command_id)
    if not cmd_info:
        return None

    cmd_template = cmd_info.get('cmd', '')

    # Substitute parameters
    try:
        cmd_string = cmd_template.format(**params)
    except KeyError as e:
        return None

    return cmd_string


# ============================================================================
# Pending Commands Queue
# ============================================================================

def load_pending_commands() -> dict:
    """Load pending commands from file"""
    if PENDING_COMMANDS_FILE.exists():
        try:
            with open(PENDING_COMMANDS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_pending_commands(commands: dict) -> None:
    """Save pending commands to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(PENDING_COMMANDS_FILE, 'w') as f:
            json.dump(commands, f, indent=2)
    except Exception as e:
        print(f"Error saving pending commands: {e}")


def queue_command(client_id: str, command_id: str, params: dict, admin_user: str) -> Optional[dict]:
    """
    Queue a command for a specific client
    Returns the signed command or None if validation fails
    """
    # Validate command is whitelisted
    cmd_info = get_whitelisted_command(command_id)
    if not cmd_info:
        return None

    # Validate and sanitize parameters
    is_valid, error_msg, sanitized_params = validate_command_params(command_id, params)
    if not is_valid:
        raise ValueError(error_msg)

    # Build the actual command
    cmd_string = build_command_string(command_id, sanitized_params)
    if not cmd_string:
        raise ValueError("Failed to build command string")

    # Create command object
    command_obj = {
        'command_uuid': str(uuid.uuid4()),
        'command_id': command_id,
        'command_string': cmd_string,
        'params': sanitized_params,
        'timeout': cmd_info.get('timeout', COMMAND_TIMEOUT_SECONDS),
        'queued_at': datetime.now().isoformat(),
        'queued_by': admin_user,
        'status': 'pending'
    }

    # Sign the command for the target client
    signed_command = sign_command(command_obj, client_id)
    if not signed_command:
        raise ValueError(f"Failed to sign command for client '{client_id}' - client not registered")

    # Store in pending queue
    pending = load_pending_commands()
    if client_id not in pending:
        pending[client_id] = []

    pending[client_id].append(signed_command)
    save_pending_commands(pending)

    # Audit log
    log_command_event('queued', signed_command, admin_user)

    return signed_command


def get_pending_commands(client_id: str) -> List[dict]:
    """Get all pending commands for a client"""
    pending = load_pending_commands()
    return pending.get(client_id, [])


def pop_pending_command(client_id: str) -> Optional[dict]:
    """Get and remove the oldest pending command for a client"""
    pending = load_pending_commands()

    if client_id not in pending or not pending[client_id]:
        return None

    command = pending[client_id].pop(0)
    save_pending_commands(pending)

    return command


def clear_pending_commands(client_id: str) -> int:
    """Clear all pending commands for a client, returns count cleared"""
    pending = load_pending_commands()

    if client_id not in pending:
        return 0

    count = len(pending[client_id])
    del pending[client_id]
    save_pending_commands(pending)

    return count


# ============================================================================
# Command Results Storage
# ============================================================================

def store_command_result(result: dict) -> None:
    """Store a command execution result"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Add server-side timestamp
    result['result_received_at'] = datetime.now().isoformat()

    # Truncate output if too large
    if 'stdout' in result and len(result.get('stdout', '')) > MAX_OUTPUT_SIZE:
        result['stdout'] = result['stdout'][:MAX_OUTPUT_SIZE] + '\n... [output truncated]'
        result['truncated'] = True

    if 'stderr' in result and len(result.get('stderr', '')) > MAX_OUTPUT_SIZE:
        result['stderr'] = result['stderr'][:MAX_OUTPUT_SIZE] + '\n... [output truncated]'
        result['truncated'] = True

    try:
        with open(COMMAND_RESULTS_FILE, 'a') as f:
            f.write(json.dumps(result) + '\n')
    except Exception as e:
        print(f"Error storing command result: {e}")

    # Audit log
    log_command_event('completed', result, result.get('client_id', 'unknown'))


def get_command_results(client_id: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Get command execution results, optionally filtered by client"""
    if not COMMAND_RESULTS_FILE.exists():
        return []

    results = []
    try:
        with open(COMMAND_RESULTS_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    if client_id is None or result.get('client_id') == client_id:
                        results.append(result)
    except Exception as e:
        print(f"Error reading command results: {e}")

    # Return most recent
    return results[-limit:]


def get_result_by_uuid(command_uuid: str) -> Optional[dict]:
    """Get a specific command result by UUID"""
    if not COMMAND_RESULTS_FILE.exists():
        return None

    try:
        with open(COMMAND_RESULTS_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    if result.get('command_uuid') == command_uuid:
                        return result
    except Exception:
        pass

    return None


# ============================================================================
# Audit Logging
# ============================================================================

def log_command_event(event_type: str, command_data: dict, user: str) -> None:
    """Log a command-related event for audit purposes"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'event_type': event_type,
        'user': user,
        'command_uuid': command_data.get('command_uuid'),
        'command_id': command_data.get('command_id'),
        'client_id': command_data.get('client_id'),
        'status': command_data.get('status'),
        'exit_code': command_data.get('exit_code')
    }

    try:
        with open(COMMAND_AUDIT_LOG, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"Error writing audit log: {e}")


def get_audit_log(limit: int = 100) -> List[dict]:
    """Get recent audit log entries"""
    if not COMMAND_AUDIT_LOG.exists():
        return []

    entries = []
    try:
        with open(COMMAND_AUDIT_LOG, 'r') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
    except Exception as e:
        print(f"Error reading audit log: {e}")

    return entries[-limit:]
