"""
Unit tests for ping_benchmark.py client
"""

import pytest
import json
import socket
import time
import threading
from unittest.mock import Mock, patch, mock_open, MagicMock
from datetime import datetime
import sys
import os

# Add parent directory to path to import ping_benchmark
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ping_benchmark import PingBenchmark


class TestConfiguration:
    """Tests for configuration loading and defaults"""

    def test_load_valid_config(self, tmp_path):
        """Test loading a valid config.json file"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "ping_target": "8.8.8.8",
            "ping_count": 10,
            "test_interval_seconds": 60,
            "results_dir": "/tmp/results",
            "center_server_url": "http://server:5000",
            "heartbeat_interval_seconds": 30,
            "client_id": "test-client"
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.router1_gw == "192.168.1.1"
        assert benchmark.router1_iface == "eth0"
        assert benchmark.router2_gw == "192.168.2.1"
        assert benchmark.router2_iface == "eth1"
        assert benchmark.ping_target == "8.8.8.8"
        assert benchmark.ping_count == 10
        assert benchmark.test_interval == 60
        assert benchmark.center_server_url == "http://server:5000"
        assert benchmark.heartbeat_interval == 30
        assert benchmark.client_id == "test-client"

    def test_client_id_defaults_to_hostname_when_empty(self, tmp_path):
        """Test that empty client_id defaults to hostname"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results"),
            "client_id": ""
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.client_id == socket.gethostname()
        assert benchmark.client_id != ""

    def test_client_id_defaults_to_hostname_when_missing(self, tmp_path):
        """Test that missing client_id defaults to hostname"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results")
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.client_id == socket.gethostname()

    def test_client_id_uses_custom_value(self, tmp_path):
        """Test that custom client_id is preserved"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results"),
            "client_id": "my-custom-client"
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.client_id == "my-custom-client"

    def test_heartbeat_interval_default(self, tmp_path):
        """Test default heartbeat interval is 60 seconds"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results")
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.heartbeat_interval == 60

    def test_center_server_url_optional(self, tmp_path):
        """Test that center_server_url can be empty"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results")
        }
        config_file.write_text(json.dumps(config_data))

        benchmark = PingBenchmark(config_file=str(config_file))

        assert benchmark.center_server_url == ""


class TestHeartbeat:
    """Tests for heartbeat functionality"""

    @pytest.fixture
    def benchmark(self, tmp_path):
        """Create a benchmark instance for testing"""
        config_file = tmp_path / "config.json"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(tmp_path / "results"),
            "center_server_url": "http://localhost:5000",
            "heartbeat_interval_seconds": 1,
            "client_id": "test-client"
        }
        config_file.write_text(json.dumps(config_data))
        return PingBenchmark(config_file=str(config_file))

    def test_heartbeat_payload_structure(self, benchmark):
        """Test that heartbeat payload contains required fields"""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            benchmark.send_heartbeat()

            # Verify urlopen was called
            assert mock_urlopen.called
            call_args = mock_urlopen.call_args

            # Extract request object
            request = call_args[0][0]
            payload = json.loads(request.data.decode('utf-8'))

            assert 'client_id' in payload
            assert 'hostname' in payload
            assert 'router1_interface' in payload
            assert 'router2_interface' in payload
            assert payload['client_id'] == 'test-client'
            assert payload['router1_interface'] == 'eth0'
            assert payload['router2_interface'] == 'eth1'

    def test_heartbeat_handles_server_unavailable(self, benchmark):
        """Test that heartbeat handles server being unavailable gracefully"""
        with patch('urllib.request.urlopen', side_effect=Exception("Connection refused")):
            # Should not raise exception
            benchmark.send_heartbeat()

    def test_heartbeat_thread_starts(self, benchmark):
        """Test that heartbeat thread starts correctly"""
        benchmark.start_heartbeat()

        assert benchmark.heartbeat_running is True
        assert benchmark.heartbeat_thread is not None
        assert benchmark.heartbeat_thread.is_alive()

        # Clean up
        benchmark.stop_heartbeat()

    def test_heartbeat_thread_stops(self, benchmark):
        """Test that heartbeat thread stops cleanly"""
        benchmark.start_heartbeat()
        assert benchmark.heartbeat_running is True

        benchmark.stop_heartbeat()

        assert benchmark.heartbeat_running is False
        time.sleep(0.5)  # Give thread time to stop

    def test_heartbeat_sent_periodically(self, benchmark):
        """Test that heartbeats are sent at configured interval"""
        call_count = 0

        def mock_send():
            nonlocal call_count
            call_count += 1

        with patch.object(benchmark, 'send_heartbeat', side_effect=mock_send):
            benchmark.start_heartbeat()
            time.sleep(2.5)  # Wait for ~2 heartbeats (interval is 1 second)
            benchmark.stop_heartbeat()

        assert call_count >= 2


class TestBenchmarkData:
    """Tests for benchmark data structure and sending"""

    @pytest.fixture
    def benchmark(self, tmp_path):
        """Create a benchmark instance for testing"""
        config_file = tmp_path / "config.json"
        results_dir = tmp_path / "results"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(results_dir),
            "center_server_url": "http://localhost:5000",
            "client_id": "test-client"
        }
        config_file.write_text(json.dumps(config_data))
        return PingBenchmark(config_file=str(config_file))

    def test_benchmark_result_includes_client_id(self, benchmark):
        """Test that benchmark results include client_id"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="64 bytes from 8.8.8.8: time=10.5 ms\n10% packet loss",
                returncode=0
            )

            result = benchmark.run_benchmark()

            assert 'client_id' in result
            assert result['client_id'] == 'test-client'

    def test_benchmark_result_includes_hostname(self, benchmark):
        """Test that benchmark results include hostname"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="64 bytes from 8.8.8.8: time=10.5 ms\n10% packet loss",
                returncode=0
            )

            result = benchmark.run_benchmark()

            assert 'hostname' in result
            assert result['hostname'] == socket.gethostname()

    def test_benchmark_result_structure(self, benchmark):
        """Test that benchmark result has correct structure"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                stdout="64 bytes from 8.8.8.8: time=10.5 ms\n0% packet loss",
                returncode=0
            )

            result = benchmark.run_benchmark()

            assert 'timestamp' in result
            assert 'client_id' in result
            assert 'hostname' in result
            assert 'router1' in result
            assert 'router2' in result
            assert isinstance(result['router1'], dict)
            assert isinstance(result['router2'], dict)

    def test_send_to_center_server_success(self, benchmark):
        """Test successful sending to center server"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'client_id': 'test-client',
            'hostname': 'test-host',
            'router1': {'packet_loss_pct': 0.0},
            'router2': {'packet_loss_pct': 0.0}
        }

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            benchmark.send_to_center_server(result)

            assert mock_urlopen.called

    def test_send_to_center_server_failure(self, benchmark):
        """Test graceful handling of send failure"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'client_id': 'test-client',
            'router1': {},
            'router2': {}
        }

        with patch('urllib.request.urlopen', side_effect=Exception("Network error")):
            # Should not raise exception
            benchmark.send_to_center_server(result)


class TestIntegration:
    """Integration tests for full benchmark cycle"""

    @pytest.fixture
    def benchmark(self, tmp_path):
        """Create a benchmark instance for testing"""
        config_file = tmp_path / "config.json"
        results_dir = tmp_path / "results"
        config_data = {
            "router1": {"gateway": "192.168.1.1", "interface": "eth0"},
            "router2": {"gateway": "192.168.2.1", "interface": "eth1"},
            "results_dir": str(results_dir),
            "center_server_url": "http://localhost:5000",
            "client_id": "integration-test-client",
            "ping_count": 5
        }
        config_file.write_text(json.dumps(config_data))
        return PingBenchmark(config_file=str(config_file))

    def test_full_benchmark_cycle(self, benchmark):
        """Test complete benchmark cycle: ping -> save -> send"""
        with patch('subprocess.run') as mock_run, \
             patch('urllib.request.urlopen') as mock_urlopen:

            # Mock ping output
            mock_run.return_value = Mock(
                stdout="64 bytes from 8.8.8.8: time=10.5 ms\n"
                       "64 bytes from 8.8.8.8: time=11.2 ms\n"
                       "64 bytes from 8.8.8.8: time=9.8 ms\n"
                       "5 packets transmitted, 3 received, 40% packet loss",
                returncode=0
            )

            # Mock server response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = benchmark.run_benchmark()

            # Verify result structure
            assert result['client_id'] == 'integration-test-client'
            assert result['hostname'] == socket.gethostname()
            assert 'timestamp' in result
            assert 'router1' in result
            assert 'router2' in result

            # Verify files were saved
            results_dir = benchmark.results_dir
            assert os.path.exists(results_dir)
            jsonl_file = os.path.join(results_dir, 'benchmark_log.jsonl')
            assert os.path.exists(jsonl_file)

            # Verify data was sent to server
            assert mock_urlopen.called
