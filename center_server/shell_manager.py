#!/usr/bin/env python3
"""
Shell Session Manager for Web Shell Feature
Manages shell sessions between admin users and client machines
"""

import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading

# Session timeout in seconds (30 minutes of inactivity)
SESSION_TIMEOUT = 1800

# Maximum concurrent sessions per client
MAX_SESSIONS_PER_CLIENT = 3


class ShellSession:
    """Represents a shell session between admin and client"""

    def __init__(self, session_id: str, client_id: str, admin_sid: str):
        self.session_id = session_id
        self.client_id = client_id
        self.admin_sid = admin_sid  # Socket.IO session ID of admin
        self.client_sid = None  # Socket.IO session ID of client
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.status = 'pending'  # pending, connected, closed
        self.rows = 24
        self.cols = 80

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()

    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity"""
        return (datetime.now() - self.last_activity).total_seconds() > SESSION_TIMEOUT

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'session_id': self.session_id,
            'client_id': self.client_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'rows': self.rows,
            'cols': self.cols
        }


class ShellSessionManager:
    """Manages all active shell sessions"""

    def __init__(self):
        self.sessions: Dict[str, ShellSession] = {}
        self.admin_sessions: Dict[str, str] = {}  # admin_sid -> session_id
        self.client_sessions: Dict[str, list] = {}  # client_id -> [session_ids]
        self.client_sids: Dict[str, str] = {}  # client_id -> client socket sid
        self.lock = threading.Lock()

        # Start cleanup thread
        self.cleanup_running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired_sessions, daemon=True)
        self.cleanup_thread.start()

    def create_session(self, client_id: str, admin_sid: str, rows: int = 24, cols: int = 80) -> Optional[ShellSession]:
        """Create a new shell session"""
        with self.lock:
            # Check if client has too many sessions
            client_session_count = len(self.client_sessions.get(client_id, []))
            if client_session_count >= MAX_SESSIONS_PER_CLIENT:
                return None

            # Check if client is connected
            if client_id not in self.client_sids:
                return None

            session_id = str(uuid.uuid4())
            session = ShellSession(session_id, client_id, admin_sid)
            session.rows = rows
            session.cols = cols

            self.sessions[session_id] = session
            self.admin_sessions[admin_sid] = session_id

            if client_id not in self.client_sessions:
                self.client_sessions[client_id] = []
            self.client_sessions[client_id].append(session_id)

            print(f"[Shell] Session created: {session_id[:8]}... for client {client_id}")
            return session

    def get_session(self, session_id: str) -> Optional[ShellSession]:
        """Get a session by ID"""
        return self.sessions.get(session_id)

    def get_session_by_admin(self, admin_sid: str) -> Optional[ShellSession]:
        """Get session by admin socket ID"""
        session_id = self.admin_sessions.get(admin_sid)
        if session_id:
            return self.sessions.get(session_id)
        return None

    def get_sessions_for_client(self, client_id: str) -> list:
        """Get all sessions for a client"""
        session_ids = self.client_sessions.get(client_id, [])
        return [self.sessions[sid] for sid in session_ids if sid in self.sessions]

    def close_session(self, session_id: str) -> bool:
        """Close a session"""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False

            session.status = 'closed'

            # Clean up references
            if session.admin_sid in self.admin_sessions:
                del self.admin_sessions[session.admin_sid]

            if session.client_id in self.client_sessions:
                if session_id in self.client_sessions[session.client_id]:
                    self.client_sessions[session.client_id].remove(session_id)

            del self.sessions[session_id]

            print(f"[Shell] Session closed: {session_id[:8]}...")
            return True

    def register_client(self, client_id: str, client_sid: str):
        """Register a client's WebSocket connection"""
        with self.lock:
            self.client_sids[client_id] = client_sid
            print(f"[Shell] Client registered for shell: {client_id}")

    def unregister_client(self, client_id: str):
        """Unregister a client's WebSocket connection"""
        with self.lock:
            if client_id in self.client_sids:
                del self.client_sids[client_id]

            # Close all sessions for this client
            session_ids = self.client_sessions.get(client_id, []).copy()
            for session_id in session_ids:
                self._close_session_internal(session_id)

            print(f"[Shell] Client unregistered: {client_id}")

    def get_client_sid(self, client_id: str) -> Optional[str]:
        """Get the socket ID for a client"""
        return self.client_sids.get(client_id)

    def is_client_connected(self, client_id: str) -> bool:
        """Check if a client is connected for shell"""
        return client_id in self.client_sids

    def get_connected_clients(self) -> list:
        """Get list of clients connected for shell"""
        return list(self.client_sids.keys())

    def _close_session_internal(self, session_id: str):
        """Internal method to close session (must hold lock)"""
        session = self.sessions.get(session_id)
        if not session:
            return

        session.status = 'closed'

        if session.admin_sid in self.admin_sessions:
            del self.admin_sessions[session.admin_sid]

        if session.client_id in self.client_sessions:
            if session_id in self.client_sessions[session.client_id]:
                self.client_sessions[session.client_id].remove(session_id)

        del self.sessions[session_id]

    def _cleanup_expired_sessions(self):
        """Background thread to clean up expired sessions"""
        while self.cleanup_running:
            time.sleep(60)  # Check every minute

            with self.lock:
                expired = [sid for sid, session in self.sessions.items() if session.is_expired()]
                for session_id in expired:
                    print(f"[Shell] Session expired: {session_id[:8]}...")
                    self._close_session_internal(session_id)

    def stop(self):
        """Stop the session manager"""
        self.cleanup_running = False


# Global session manager instance
shell_manager = ShellSessionManager()
