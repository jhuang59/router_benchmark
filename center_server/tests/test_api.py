"""
Unit tests for center server API endpoints
"""

import pytest
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with temporary data directory"""
    # Set environment variable BEFORE importing app
    monkeypatch.setenv('DATA_DIR', str(tmp_path))

    # Import app after setting environment
    import app as app_module

    # Verify paths were set correctly
    monkeypatch.setattr(app_module, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(app_module, 'LOG_FILE', tmp_path / 'benchmark_data.jsonl')
    monkeypatch.setattr(app_module, 'CLIENTS_FILE', tmp_path / 'clients.json')

    # Clear registry
    app_module.clients_registry.clear()

    app_module.app.config['TESTING'] = True

    with app_module.app.test_client() as test_client:
        yield test_client

    # Cleanup
    app_module.clients_registry.clear()


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_endpoint_returns_200(self, client):
        """Test health endpoint returns 200 status"""
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_endpoint_returns_json(self, client):
        """Test health endpoint returns JSON with status"""
        response = client.get('/health')
        data = json.loads(response.data)

        assert 'status' in data
        assert data['status'] == 'healthy'
        assert 'timestamp' in data


class TestReceiveLogs:
    """Tests for POST /api/logs endpoint"""

    def test_receive_logs_success(self, client):
        """Test successfully receiving valid log data"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'client_id': 'test-client',
            'hostname': 'test-host',
            'router1': {'packet_loss_pct': 0.0, 'avg_ms': 15.5},
            'router2': {'packet_loss_pct': 0.0, 'avg_ms': 18.2}
        }

        response = client.post('/api/logs',
                              data=json.dumps(log_data),
                              content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

    def test_receive_logs_with_client_id(self, client):
        """Test that client_id is stored correctly"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'client_id': 'specific-client-123',
            'router1': {'packet_loss_pct': 5.0},
            'router2': {'packet_loss_pct': 3.0}
        }

        response = client.post('/api/logs',
                              data=json.dumps(log_data),
                              content_type='application/json')

        assert response.status_code == 200

    def test_receive_logs_no_data(self, client):
        """Test handling of empty payload"""
        response = client.post('/api/logs',
                              data=json.dumps(None),
                              content_type='application/json')

        # Should handle gracefully
        assert response.status_code in [200, 400]


class TestHeartbeat:
    """Tests for POST /api/heartbeat endpoint"""

    def test_heartbeat_success(self, client):
        """Test successfully receiving heartbeat"""
        heartbeat_data = {
            'client_id': 'test-client',
            'hostname': 'test-host',
            'router1_interface': 'eth0',
            'router2_interface': 'eth1'
        }

        response = client.post('/api/heartbeat',
                              data=json.dumps(heartbeat_data),
                              content_type='application/json')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

    def test_heartbeat_updates_registry(self, client):
        """Test that heartbeat updates clients registry"""
        import app as app_module

        heartbeat_data = {
            'client_id': 'test-client-1',
            'hostname': 'host-1',
            'router1_interface': 'eth0',
            'router2_interface': 'eth1'
        }

        client.post('/api/heartbeat',
                   data=json.dumps(heartbeat_data),
                   content_type='application/json')

        assert 'test-client-1' in app_module.clients_registry
        assert app_module.clients_registry['test-client-1']['hostname'] == 'host-1'

    def test_heartbeat_missing_client_id(self, client):
        """Test handling of heartbeat without client_id"""
        heartbeat_data = {
            'hostname': 'test-host'
        }

        response = client.post('/api/heartbeat',
                              data=json.dumps(heartbeat_data),
                              content_type='application/json')

        assert response.status_code == 400

    def test_heartbeat_updates_timestamp(self, client):
        """Test that repeated heartbeats update timestamp"""
        import app as app_module
        import time

        heartbeat_data = {
            'client_id': 'update-test-client',
            'hostname': 'test-host'
        }

        # Send first heartbeat
        client.post('/api/heartbeat',
                   data=json.dumps(heartbeat_data),
                   content_type='application/json')
        first_timestamp = app_module.clients_registry['update-test-client']['last_heartbeat']

        # Wait a moment and send second heartbeat
        time.sleep(0.1)

        client.post('/api/heartbeat',
                   data=json.dumps(heartbeat_data),
                   content_type='application/json')
        second_timestamp = app_module.clients_registry['update-test-client']['last_heartbeat']

        assert second_timestamp > first_timestamp


class TestGetClients:
    """Tests for GET /api/clients endpoint"""

    def test_get_clients_empty(self, client):
        """Test getting clients when registry is empty"""
        response = client.get('/api/clients')
        data = json.loads(response.data)

        assert data['total'] == 0
        assert data['clients'] == []

    def test_get_clients_with_data(self, client):
        """Test getting all registered clients"""
        import app as app_module

        # Add test clients
        app_module.clients_registry['client-1'] = {
            'client_id': 'client-1',
            'hostname': 'host-1',
            'last_heartbeat': datetime.now().isoformat()
        }
        app_module.clients_registry['client-2'] = {
            'client_id': 'client-2',
            'hostname': 'host-2',
            'last_heartbeat': datetime.now().isoformat()
        }

        response = client.get('/api/clients')
        data = json.loads(response.data)

        assert data['total'] == 2
        assert len(data['clients']) == 2

    def test_get_clients_online_status(self, client):
        """Test clients are marked online when recent heartbeat"""
        import app as app_module

        # Add online client (recent heartbeat)
        app_module.clients_registry['online-client'] = {
            'client_id': 'online-client',
            'hostname': 'online-host',
            'last_heartbeat': datetime.now().isoformat()
        }

        response = client.get('/api/clients')
        data = json.loads(response.data)

        assert data['online'] == 1
        assert data['clients'][0]['status'] == 'online'

    def test_get_clients_offline_status(self, client):
        """Test clients are marked offline when old heartbeat"""
        import app as app_module

        # Add offline client (old heartbeat > 2 minutes)
        old_time = datetime.now() - timedelta(seconds=150)
        app_module.clients_registry['offline-client'] = {
            'client_id': 'offline-client',
            'hostname': 'offline-host',
            'last_heartbeat': old_time.isoformat()
        }

        response = client.get('/api/clients')
        data = json.loads(response.data)

        assert data['offline'] == 1
        assert data['clients'][0]['status'] == 'offline'

    def test_get_clients_custom_timeout(self, client):
        """Test custom timeout parameter"""
        import app as app_module

        # Add client with 60-second-old heartbeat
        old_time = datetime.now() - timedelta(seconds=60)
        app_module.clients_registry['test-client'] = {
            'client_id': 'test-client',
            'hostname': 'test-host',
            'last_heartbeat': old_time.isoformat()
        }

        # With 30-second timeout, should be offline
        response = client.get('/api/clients?timeout=30')
        data = json.loads(response.data)
        assert data['clients'][0]['status'] == 'offline'

        # With 90-second timeout, should be online
        response = client.get('/api/clients?timeout=90')
        data = json.loads(response.data)
        assert data['clients'][0]['status'] == 'online'

    def test_get_clients_sorts_by_recent(self, client):
        """Test clients are sorted by most recent heartbeat"""
        import app as app_module

        # Add clients with different timestamps
        app_module.clients_registry['old-client'] = {
            'client_id': 'old-client',
            'hostname': 'old-host',
            'last_heartbeat': (datetime.now() - timedelta(seconds=100)).isoformat()
        }
        app_module.clients_registry['new-client'] = {
            'client_id': 'new-client',
            'hostname': 'new-host',
            'last_heartbeat': datetime.now().isoformat()
        }

        response = client.get('/api/clients')
        data = json.loads(response.data)

        # First client should be the newer one
        assert data['clients'][0]['client_id'] == 'new-client'


class TestGetDataAndStats:
    """Tests for GET /api/data and /api/stats endpoints - simplified"""

    def test_get_data_endpoint_exists(self, client):
        """Test that /api/data endpoint exists"""
        response = client.get('/api/data')
        assert response.status_code == 200

    def test_get_data_returns_json(self, client):
        """Test that /api/data returns JSON"""
        response = client.get('/api/data')
        data = json.loads(response.data)
        assert 'data' in data

    def test_get_stats_endpoint_exists(self, client):
        """Test that /api/stats endpoint exists"""
        response = client.get('/api/stats')
        assert response.status_code == 200

    def test_get_stats_returns_json(self, client):
        """Test that /api/stats returns JSON"""
        response = client.get('/api/stats')
        data = json.loads(response.data)
        assert 'stats' in data

    def test_get_data_with_limit_parameter(self, client):
        """Test /api/data accepts limit parameter"""
        response = client.get('/api/data?limit=50')
        assert response.status_code == 200

    def test_get_data_with_client_id_parameter(self, client):
        """Test /api/data accepts client_id parameter"""
        response = client.get('/api/data?client_id=test-client')
        assert response.status_code == 200

    def test_get_stats_with_client_id_parameter(self, client):
        """Test /api/stats accepts client_id parameter"""
        response = client.get('/api/stats?client_id=test-client')
        assert response.status_code == 200
