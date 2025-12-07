#!/usr/bin/env python3
"""
Router Ping Benchmark Tool
Pings internet through two different routers and summarizes performance
Includes remote command execution with mutual authentication
"""

import subprocess
import json
import time
import statistics
from datetime import datetime, timedelta
import os
import re
import urllib.request
import urllib.error
import threading
import socket
import hmac
import hashlib

class PingBenchmark:
    def __init__(self, config_file='config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        self.router1_gw = self.config['router1']['gateway']
        self.router1_iface = self.config['router1']['interface']
        self.router2_gw = self.config['router2']['gateway']
        self.router2_iface = self.config['router2']['interface']
        self.ping_target = self.config.get('ping_target', '8.8.8.8')
        self.ping_count = self.config.get('ping_count', 20)
        self.test_interval = self.config.get('test_interval_seconds', 300)
        self.results_dir = self.config.get('results_dir', '/app/results')
        self.center_server_url = self.config.get('center_server_url', '')
        self.heartbeat_interval = self.config.get('heartbeat_interval_seconds', 60)
        # Use hostname if client_id is empty or not specified
        self.client_id = self.config.get('client_id') or socket.gethostname()

        # Authentication settings
        self.secret_key = self.config.get('secret_key', '')
        self.command_poll_interval = self.config.get('command_poll_interval_seconds', 10)
        self.command_enabled = self.config.get('remote_commands_enabled', True)

        # Heartbeat thread control
        self.heartbeat_running = False
        self.heartbeat_thread = None

        # Command polling thread control
        self.command_polling_running = False
        self.command_polling_thread = None
        self.used_nonces = set()  # Track used nonces to prevent replay attacks
        self.nonce_cleanup_time = datetime.now()

        # Create results directory
        os.makedirs(self.results_dir, exist_ok=True)
    
    def ping_through_router(self, gateway, interface, name):
        """
        Ping through a specific router using source interface
        Returns dict with latency statistics and packet loss
        """
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Testing {name}...")
        print(f"  Gateway: {gateway}, Interface: {interface}")
        
        cmd = [
            'ping',
            '-I', interface,
            '-c', str(self.ping_count),
            '-W', '2',  # 2 second timeout
            self.ping_target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.ping_count * 3
            )
            
            output = result.stdout
            
            # Parse packet loss
            loss_match = re.search(r'(\d+)% packet loss', output)
            packet_loss = float(loss_match.group(1)) if loss_match else 100.0
            
            # Parse latency stats
            latencies = []
            for line in output.split('\n'):
                if 'time=' in line:
                    time_match = re.search(r'time=([\d.]+)', line)
                    if time_match:
                        latencies.append(float(time_match.group(1)))
            
            stats = {
                'timestamp': datetime.now().isoformat(),
                'router': name,
                'gateway': gateway,
                'interface': interface,
                'target': self.ping_target,
                'packet_loss_pct': packet_loss,
                'packets_sent': self.ping_count,
                'packets_received': len(latencies),
                'success': packet_loss < 100
            }
            
            if latencies:
                stats.update({
                    'min_ms': min(latencies),
                    'max_ms': max(latencies),
                    'avg_ms': statistics.mean(latencies),
                    'median_ms': statistics.median(latencies),
                    'stdev_ms': statistics.stdev(latencies) if len(latencies) > 1 else 0
                })
            else:
                stats.update({
                    'min_ms': None,
                    'max_ms': None,
                    'avg_ms': None,
                    'median_ms': None,
                    'stdev_ms': None
                })
            
            return stats
            
        except subprocess.TimeoutExpired:
            print(f"  ERROR: Ping timeout for {name}")
            return {
                'timestamp': datetime.now().isoformat(),
                'router': name,
                'gateway': gateway,
                'interface': interface,
                'target': self.ping_target,
                'packet_loss_pct': 100.0,
                'packets_sent': self.ping_count,
                'packets_received': 0,
                'success': False,
                'error': 'timeout'
            }
        except Exception as e:
            print(f"  ERROR: {str(e)}")
            return {
                'timestamp': datetime.now().isoformat(),
                'router': name,
                'gateway': gateway,
                'interface': interface,
                'target': self.ping_target,
                'success': False,
                'error': str(e)
            }
    
    def run_benchmark(self):
        """Run ping benchmark on both routers"""
        print(f"\n{'='*60}")
        print(f"Starting Ping Benchmark - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        # Test both routers
        router1_result = self.ping_through_router(
            self.router1_gw, 
            self.router1_iface, 
            'Router 1'
        )
        
        router2_result = self.ping_through_router(
            self.router2_gw, 
            self.router2_iface, 
            'Router 2'
        )
        
        # Combine results
        benchmark_result = {
            'timestamp': datetime.now().isoformat(),
            'client_id': self.client_id,
            'hostname': socket.gethostname(),
            'router1': router1_result,
            'router2': router2_result
        }
        
        # Print summary
        self.print_summary(benchmark_result)

        # Save results
        self.save_results(benchmark_result)

        # Send to center server
        self.send_to_center_server(benchmark_result)

        return benchmark_result
    
    def print_summary(self, result):
        """Print formatted summary of benchmark results"""
        print(f"\n{'='*60}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*60}")
        
        for router_key in ['router1', 'router2']:
            r = result[router_key]
            print(f"\n{r['router']}:")
            print(f"  Interface: {r['interface']}")
            print(f"  Gateway: {r['gateway']}")
            print(f"  Packet Loss: {r['packet_loss_pct']:.1f}%")
            
            if r['success'] and r.get('avg_ms') is not None:
                print(f"  Latency:")
                print(f"    Min:    {r['min_ms']:.2f} ms")
                print(f"    Avg:    {r['avg_ms']:.2f} ms")
                print(f"    Median: {r['median_ms']:.2f} ms")
                print(f"    Max:    {r['max_ms']:.2f} ms")
                print(f"    StdDev: {r['stdev_ms']:.2f} ms")
            else:
                print(f"  Status: FAILED - {r.get('error', 'No response')}")
        
        # Compare routers
        print(f"\n{'='*60}")
        print("COMPARISON:")
        print(f"{'='*60}")
        
        r1 = result['router1']
        r2 = result['router2']
        
        if r1['success'] and r2['success']:
            if r1.get('avg_ms') and r2.get('avg_ms'):
                diff = r1['avg_ms'] - r2['avg_ms']
                if abs(diff) < 1:
                    print("Both routers have similar performance")
                elif diff < 0:
                    print(f"Router 1 is FASTER by {abs(diff):.2f} ms average")
                else:
                    print(f"Router 2 is FASTER by {diff:.2f} ms average")
            
            loss_diff = r1['packet_loss_pct'] - r2['packet_loss_pct']
            if loss_diff > 0:
                print(f"Router 2 has BETTER packet loss by {loss_diff:.1f}%")
            elif loss_diff < 0:
                print(f"Router 1 has BETTER packet loss by {abs(loss_diff):.1f}%")
        else:
            if not r1['success']:
                print("Router 1: FAILED")
            if not r2['success']:
                print("Router 2: FAILED")
        
        print(f"{'='*60}\n")
    
    def save_results(self, result):
        """Save results to JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.results_dir}/benchmark_{timestamp}.json"

        with open(filename, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"Results saved to: {filename}")

        # Also append to a cumulative log
        log_file = f"{self.results_dir}/benchmark_log.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(result) + '\n')

    def send_to_center_server(self, result):
        """Send results to center server"""
        if not self.center_server_url:
            return

        try:
            url = f"{self.center_server_url}/api/logs"
            data = json.dumps(result).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f"Successfully sent data to center server: {url}")
                else:
                    print(f"Warning: Center server returned status {response.status}")

        except urllib.error.URLError as e:
            print(f"Warning: Failed to send data to center server: {e}")
        except Exception as e:
            print(f"Warning: Error sending to center server: {e}")

    def send_heartbeat(self):
        """Send heartbeat signal to center server"""
        if not self.center_server_url:
            return

        try:
            url = f"{self.center_server_url}/api/heartbeat"
            heartbeat_data = {
                'client_id': self.client_id,
                'hostname': socket.gethostname(),
                'router1_interface': self.router1_iface,
                'router2_interface': self.router2_iface,
            }
            data = json.dumps(heartbeat_data).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat sent to center server")

        except Exception as e:
            print(f"Warning: Heartbeat failed: {e}")

    def heartbeat_worker(self):
        """Background worker that sends periodic heartbeats"""
        print(f"Heartbeat worker started (interval: {self.heartbeat_interval}s)")

        while self.heartbeat_running:
            self.send_heartbeat()
            time.sleep(self.heartbeat_interval)

    def start_heartbeat(self):
        """Start the heartbeat background thread"""
        if not self.center_server_url:
            print("No center server configured, heartbeat disabled")
            return

        if self.heartbeat_running:
            return

        self.heartbeat_running = True
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_worker, daemon=True)
        self.heartbeat_thread.start()
        print(f"Heartbeat started for client: {self.client_id}")

    def stop_heartbeat(self):
        """Stop the heartbeat background thread"""
        if self.heartbeat_running:
            self.heartbeat_running = False
            if self.heartbeat_thread:
                self.heartbeat_thread.join(timeout=2)

    # =========================================================================
    # Remote Command Execution (with mutual authentication)
    # =========================================================================

    def verify_command_signature(self, command_data):
        """
        Verify a command's HMAC signature and check for replay attacks
        Returns (is_valid, error_message)
        """
        if not self.secret_key:
            return False, "No secret key configured"

        # Check required fields
        required_fields = ['timestamp', 'nonce', 'signature']
        for field in required_fields:
            if field not in command_data:
                return False, f"Missing required field: {field}"

        # Extract signature
        signature = command_data.get('signature')

        # Create a copy without signature for verification
        payload = {k: v for k, v in command_data.items() if k != 'signature'}

        # Canonicalize and compute expected signature
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        expected_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Verify signature
        if not hmac.compare_digest(signature, expected_signature):
            return False, "Invalid signature - command rejected"

        # Check timestamp (prevent replay of old commands)
        try:
            cmd_time = datetime.fromisoformat(command_data['timestamp'])
            now = datetime.now()
            time_diff = abs((now - cmd_time).total_seconds())

            if time_diff > 300:  # 5 minutes tolerance
                return False, f"Command expired (timestamp too old: {time_diff:.0f}s)"
        except ValueError as e:
            return False, f"Invalid timestamp format: {e}"

        # Check nonce (prevent replay attacks)
        nonce = command_data['nonce']

        # Clean up old nonces periodically
        if (datetime.now() - self.nonce_cleanup_time).total_seconds() > 600:
            self.used_nonces.clear()
            self.nonce_cleanup_time = datetime.now()

        if nonce in self.used_nonces:
            return False, "Nonce already used (replay attack detected)"

        # Mark nonce as used
        self.used_nonces.add(nonce)

        return True, "Valid"

    def execute_command(self, command_data):
        """
        Execute a verified command and return the result
        """
        command_string = command_data.get('command_string', '')
        timeout = command_data.get('timeout', 60)
        command_uuid = command_data.get('command_uuid', '')
        command_id = command_data.get('command_id', '')

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Executing command: {command_id}")
        print(f"  Command: {command_string}")

        start_time = time.time()

        try:
            result = subprocess.run(
                command_string,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            duration = time.time() - start_time

            return {
                'command_uuid': command_uuid,
                'command_id': command_id,
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'executed_at': datetime.now().isoformat(),
                'duration_seconds': round(duration, 3)
            }

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                'command_uuid': command_uuid,
                'command_id': command_id,
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Command timed out after {timeout} seconds',
                'executed_at': datetime.now().isoformat(),
                'duration_seconds': round(duration, 3),
                'error': 'timeout'
            }

        except Exception as e:
            duration = time.time() - start_time
            return {
                'command_uuid': command_uuid,
                'command_id': command_id,
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e),
                'executed_at': datetime.now().isoformat(),
                'duration_seconds': round(duration, 3),
                'error': str(e)
            }

    def submit_command_result(self, result):
        """Submit command execution result to center server"""
        if not self.center_server_url:
            return

        try:
            url = f"{self.center_server_url}/api/commands/result"
            data = json.dumps(result).encode('utf-8')

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'X-Client-ID': self.client_id,
                    'X-Client-API-Key': self.secret_key
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Command result submitted")
                else:
                    print(f"Warning: Failed to submit result, status {response.status}")

        except Exception as e:
            print(f"Warning: Failed to submit command result: {e}")

    def poll_for_commands(self):
        """Poll the center server for pending commands"""
        if not self.center_server_url or not self.secret_key:
            return None

        try:
            url = f"{self.center_server_url}/api/commands/poll"

            req = urllib.request.Request(
                url,
                headers={
                    'X-Client-ID': self.client_id,
                    'X-Client-API-Key': self.secret_key
                },
                method='GET'
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get('has_command'):
                        return data.get('command')
                return None

        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"Warning: Authentication failed - check secret_key configuration")
            return None
        except Exception as e:
            # Silently fail - server might be temporarily unavailable
            return None

    def command_polling_worker(self):
        """Background worker that polls for and executes commands"""
        print(f"Command polling worker started (interval: {self.command_poll_interval}s)")

        while self.command_polling_running:
            try:
                # Poll for command
                command = self.poll_for_commands()

                if command:
                    # Verify signature before execution
                    is_valid, error_msg = self.verify_command_signature(command)

                    if is_valid:
                        # Execute the command
                        result = self.execute_command(command)

                        # Submit result
                        self.submit_command_result(result)

                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Command completed: exit_code={result['exit_code']}")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Command REJECTED: {error_msg}")
                        # Submit rejection result
                        self.submit_command_result({
                            'command_uuid': command.get('command_uuid', 'unknown'),
                            'command_id': command.get('command_id', 'unknown'),
                            'exit_code': -1,
                            'stdout': '',
                            'stderr': f'Command rejected: {error_msg}',
                            'executed_at': datetime.now().isoformat(),
                            'duration_seconds': 0,
                            'error': 'signature_verification_failed'
                        })

            except Exception as e:
                print(f"Warning: Error in command polling: {e}")

            time.sleep(self.command_poll_interval)

    def start_command_polling(self):
        """Start the command polling background thread"""
        if not self.center_server_url:
            print("No center server configured, command polling disabled")
            return

        if not self.secret_key:
            print("No secret key configured, command polling disabled")
            return

        if not self.command_enabled:
            print("Remote commands disabled in config")
            return

        if self.command_polling_running:
            return

        self.command_polling_running = True
        self.command_polling_thread = threading.Thread(
            target=self.command_polling_worker,
            daemon=True
        )
        self.command_polling_thread.start()
        print(f"Command polling started for client: {self.client_id}")

    def stop_command_polling(self):
        """Stop the command polling background thread"""
        if self.command_polling_running:
            self.command_polling_running = False
            if self.command_polling_thread:
                self.command_polling_thread.join(timeout=2)

    def run_continuous(self):
        """Run benchmark continuously at specified interval"""
        print(f"Starting continuous benchmarking...")
        print(f"Client ID: {self.client_id}")
        print(f"Test interval: {self.test_interval} seconds")
        if self.center_server_url:
            print(f"Heartbeat interval: {self.heartbeat_interval} seconds")
        if self.secret_key and self.command_enabled:
            print(f"Remote commands: ENABLED (poll interval: {self.command_poll_interval}s)")
        else:
            print(f"Remote commands: DISABLED")
        print(f"Press Ctrl+C to stop\n")

        # Start heartbeat in background
        self.start_heartbeat()

        # Start command polling in background
        self.start_command_polling()

        try:
            while True:
                self.run_benchmark()
                print(f"\nNext test in {self.test_interval} seconds...")
                time.sleep(self.test_interval)
        except KeyboardInterrupt:
            print("\n\nBenchmarking stopped by user")
            self.stop_command_polling()
            self.stop_heartbeat()

if __name__ == '__main__':
    benchmark = PingBenchmark()
    benchmark.run_continuous()
