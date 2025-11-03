#!/usr/bin/env python3
"""
Router Ping Benchmark Tool
Pings internet through two different routers and summarizes performance
"""

import subprocess
import json
import time
import statistics
from datetime import datetime
import os
import re
import urllib.request
import urllib.error

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
    
    def run_continuous(self):
        """Run benchmark continuously at specified interval"""
        print(f"Starting continuous benchmarking...")
        print(f"Test interval: {self.test_interval} seconds")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.run_benchmark()
                print(f"\nNext test in {self.test_interval} seconds...")
                time.sleep(self.test_interval)
        except KeyboardInterrupt:
            print("\n\nBenchmarking stopped by user")

if __name__ == '__main__':
    benchmark = PingBenchmark()
    benchmark.run_continuous()
