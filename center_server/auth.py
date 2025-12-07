#!/usr/bin/env python3
"""
Authentication utilities for Remote Command Execution
Provides HMAC-based mutual authentication between server and clients
"""

import hmac
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import os

# Configuration
DATA_DIR = Path(os.environ.get('DATA_DIR', '/app/data'))
CLIENTS_SECRETS_FILE = DATA_DIR / 'client_secrets.json'
ADMIN_SECRETS_FILE = DATA_DIR / 'admin_secrets.json'
USED_NONCES_FILE = DATA_DIR / 'used_nonces.json'

# Security settings
TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes
NONCE_EXPIRY_SECONDS = 600  # 10 minutes - nonces older than this are cleaned up


def generate_secret_key(length: int = 32) -> str:
    """Generate a cryptographically secure secret key"""
    return secrets.token_hex(length)


def generate_nonce() -> str:
    """Generate a unique nonce for replay attack prevention"""
    return secrets.token_hex(16)


# ============================================================================
# Client Secrets Management
# ============================================================================

def load_client_secrets() -> dict:
    """Load client secrets from file"""
    if CLIENTS_SECRETS_FILE.exists():
        try:
            with open(CLIENTS_SECRETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading client secrets: {e}")
            return {}
    return {}


def save_client_secrets(secrets_dict: dict) -> None:
    """Save client secrets to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CLIENTS_SECRETS_FILE, 'w') as f:
            json.dump(secrets_dict, f, indent=2)
        # Set restrictive permissions
        os.chmod(CLIENTS_SECRETS_FILE, 0o600)
    except Exception as e:
        print(f"Error saving client secrets: {e}")


def register_client(client_id: str) -> str:
    """
    Register a new client and generate its secret key
    Returns the generated secret key (show this to the user once!)
    """
    secrets_dict = load_client_secrets()

    if client_id in secrets_dict:
        raise ValueError(f"Client '{client_id}' already registered")

    secret_key = generate_secret_key()
    secrets_dict[client_id] = {
        'secret_key': secret_key,
        'created_at': datetime.now().isoformat(),
        'enabled': True
    }

    save_client_secrets(secrets_dict)
    return secret_key


def get_client_secret(client_id: str) -> Optional[str]:
    """Get the secret key for a client"""
    secrets_dict = load_client_secrets()
    client_info = secrets_dict.get(client_id)

    if client_info and client_info.get('enabled', True):
        return client_info.get('secret_key')
    return None


def revoke_client(client_id: str) -> bool:
    """Revoke a client's access"""
    secrets_dict = load_client_secrets()

    if client_id in secrets_dict:
        secrets_dict[client_id]['enabled'] = False
        secrets_dict[client_id]['revoked_at'] = datetime.now().isoformat()
        save_client_secrets(secrets_dict)
        return True
    return False


def list_clients() -> list:
    """List all registered clients"""
    secrets_dict = load_client_secrets()
    clients = []
    for client_id, info in secrets_dict.items():
        clients.append({
            'client_id': client_id,
            'created_at': info.get('created_at'),
            'enabled': info.get('enabled', True),
            'revoked_at': info.get('revoked_at')
        })
    return clients


# ============================================================================
# Admin Secrets Management
# ============================================================================

def load_admin_secrets() -> dict:
    """Load admin API keys from file"""
    if ADMIN_SECRETS_FILE.exists():
        try:
            with open(ADMIN_SECRETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading admin secrets: {e}")
            return {}
    return {}


def save_admin_secrets(secrets_dict: dict) -> None:
    """Save admin secrets to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(ADMIN_SECRETS_FILE, 'w') as f:
            json.dump(secrets_dict, f, indent=2)
        os.chmod(ADMIN_SECRETS_FILE, 0o600)
    except Exception as e:
        print(f"Error saving admin secrets: {e}")


def create_admin_key(admin_name: str) -> str:
    """Create a new admin API key"""
    secrets_dict = load_admin_secrets()

    api_key = generate_secret_key()
    secrets_dict[api_key] = {
        'name': admin_name,
        'created_at': datetime.now().isoformat(),
        'enabled': True
    }

    save_admin_secrets(secrets_dict)
    return api_key


def validate_admin_key(api_key: str) -> bool:
    """Validate an admin API key"""
    secrets_dict = load_admin_secrets()
    admin_info = secrets_dict.get(api_key)

    return admin_info is not None and admin_info.get('enabled', True)


def revoke_admin_key(api_key: str) -> bool:
    """Revoke an admin API key"""
    secrets_dict = load_admin_secrets()

    if api_key in secrets_dict:
        secrets_dict[api_key]['enabled'] = False
        secrets_dict[api_key]['revoked_at'] = datetime.now().isoformat()
        save_admin_secrets(secrets_dict)
        return True
    return False


# ============================================================================
# HMAC Signing and Verification
# ============================================================================

def create_signature(payload: dict, secret_key: str) -> str:
    """
    Create HMAC-SHA256 signature for a payload
    The payload should include timestamp and nonce for replay protection
    """
    # Canonicalize the payload (sorted keys, no spaces)
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))

    signature = hmac.new(
        secret_key.encode('utf-8'),
        canonical.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return signature


def verify_signature(payload: dict, signature: str, secret_key: str) -> bool:
    """
    Verify HMAC-SHA256 signature of a payload
    """
    expected_signature = create_signature(payload, secret_key)
    return hmac.compare_digest(signature, expected_signature)


def sign_command(command_data: dict, client_id: str) -> Optional[dict]:
    """
    Sign a command for a specific client
    Returns the command with signature, timestamp, and nonce added
    """
    secret_key = get_client_secret(client_id)
    if not secret_key:
        return None

    # Add security fields
    signed_command = command_data.copy()
    signed_command['timestamp'] = datetime.now().isoformat()
    signed_command['nonce'] = generate_nonce()
    signed_command['client_id'] = client_id

    # Create signature (excluding the signature field itself)
    signature = create_signature(signed_command, secret_key)
    signed_command['signature'] = signature

    return signed_command


def verify_command_signature(command_data: dict, secret_key: str) -> Tuple[bool, str]:
    """
    Verify a command's signature and check for replay attacks
    Returns (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['timestamp', 'nonce', 'signature']
    for field in required_fields:
        if field not in command_data:
            return False, f"Missing required field: {field}"

    # Extract and remove signature for verification
    signature = command_data.pop('signature')

    # Verify signature
    if not verify_signature(command_data, signature, secret_key):
        command_data['signature'] = signature  # Restore for debugging
        return False, "Invalid signature"

    # Restore signature
    command_data['signature'] = signature

    # Check timestamp (prevent replay of old commands)
    try:
        cmd_time = datetime.fromisoformat(command_data['timestamp'])
        now = datetime.now()
        time_diff = abs((now - cmd_time).total_seconds())

        if time_diff > TIMESTAMP_TOLERANCE_SECONDS:
            return False, f"Command expired (timestamp too old: {time_diff:.0f}s)"
    except ValueError as e:
        return False, f"Invalid timestamp format: {e}"

    # Check nonce (prevent replay attacks)
    nonce = command_data['nonce']
    if is_nonce_used(nonce):
        return False, "Nonce already used (replay attack detected)"

    # Mark nonce as used
    mark_nonce_used(nonce)

    return True, "Valid"


# ============================================================================
# Nonce Management (Replay Attack Prevention)
# ============================================================================

def load_used_nonces() -> dict:
    """Load used nonces from file"""
    if USED_NONCES_FILE.exists():
        try:
            with open(USED_NONCES_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_used_nonces(nonces: dict) -> None:
    """Save used nonces to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(USED_NONCES_FILE, 'w') as f:
            json.dump(nonces, f)
    except Exception as e:
        print(f"Error saving nonces: {e}")


def is_nonce_used(nonce: str) -> bool:
    """Check if a nonce has already been used"""
    nonces = load_used_nonces()
    return nonce in nonces


def mark_nonce_used(nonce: str) -> None:
    """Mark a nonce as used"""
    nonces = load_used_nonces()
    nonces[nonce] = datetime.now().isoformat()

    # Clean up old nonces while we're here
    cleanup_old_nonces(nonces)

    save_used_nonces(nonces)


def cleanup_old_nonces(nonces: dict) -> None:
    """Remove nonces older than NONCE_EXPIRY_SECONDS"""
    now = datetime.now()
    expired = []

    for nonce, timestamp_str in nonces.items():
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            if (now - timestamp).total_seconds() > NONCE_EXPIRY_SECONDS:
                expired.append(nonce)
        except ValueError:
            expired.append(nonce)

    for nonce in expired:
        del nonces[nonce]


# ============================================================================
# Request Authentication Decorators/Helpers
# ============================================================================

def authenticate_client_request(client_id: str, api_key: str) -> Tuple[bool, str]:
    """
    Authenticate a client request using API key
    Returns (is_valid, error_message)
    """
    secret_key = get_client_secret(client_id)

    if not secret_key:
        return False, "Client not registered or disabled"

    if api_key != secret_key:
        return False, "Invalid API key"

    return True, "Valid"


def authenticate_admin_request(api_key: str) -> Tuple[bool, str]:
    """
    Authenticate an admin request using API key
    Returns (is_valid, error_message)
    """
    if not api_key:
        return False, "No API key provided"

    if not validate_admin_key(api_key):
        return False, "Invalid or revoked admin API key"

    return True, "Valid"
