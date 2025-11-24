# Router Benchmark

A distributed system for benchmarking router performance across multiple locations with centralized visualization.
![img_v3_02sb_e11c695f-972b-42df-aeec-1226729d3deg](https://github.com/user-attachments/assets/158a64e6-0030-4b34-98a3-5e18c2688ce7)

## Architecture

This project consists of two stages:

### Stage 1: Benchmark Clients
- **Location**: Deploy on machines with multiple network interfaces connected to different routers
- **Function**: Continuously ping a target through different routers and collect performance metrics
- **Output**: Local JSON logs + sends data to center server

### Stage 2: Center Server
- **Location**: Deploy on a central server (cloud or local)
- **Function**: Collects logs from all benchmark clients and provides web-based visualization
- **Features**: Real-time dashboard with packet loss and latency charts

## Quick Start

### Deploy Center Server (Stage 2)

1. On your central server:
```bash
cd center_server
docker-compose up -d
```

2. Access dashboard at `http://YOUR_SERVER_IP:5000`

See [center_server/README.md](center_server/README.md) for detailed documentation.

### Deploy Benchmark Clients (Stage 1)

1. On each client machine:

```bash
# Update config.json with your router interfaces and center server URL
nano config.json
```

2. Configure network interfaces:
```json
{
  "router1": {
    "gateway": "192.168.1.1",
    "interface": "eth0"
  },
  "router2": {
    "gateway": "192.168.30.1",
    "interface": "eth1"
  },
  "center_server_url": "http://YOUR_CENTER_SERVER_IP:5000"
}
```

3. Deploy:
```bash
docker-compose up -d
```

## Features

### Client Features
- Ping tests through multiple routers simultaneously
- Configurable test intervals and ping counts
- Local result storage (JSON format)
- Automatic log forwarding to center server
- Heartbeat/keepalive signals to track client status
- Detailed latency statistics (min, max, avg, median, stdev)
- Packet loss tracking

### Server Features
- REST API for log collection
- Client monitoring with heartbeat tracking
- Active clients list showing online/offline status
- **Per-client data filtering**: View specific client or all clients
- Web-based dashboard
- Real-time visualization with Chart.js
- Time-series charts for packet loss and latency
- Color-coded statistics (green/yellow/red)
- Auto-refresh dashboard
- Configurable time ranges

## Use Cases

1. **Multi-Location Network Monitoring**: Deploy clients in different offices/locations
2. **ISP Comparison**: Compare performance across different internet providers
3. **Failover Testing**: Monitor primary and backup connections
4. **Network Quality Analysis**: Track network performance over time

## Data Flow

```
┌─────────────┐
│  Client 1   │──┐
│ (Router A+B)│  │
└─────────────┘  │
                 │    HTTP POST
┌─────────────┐  │   ┌─────────────┐
│  Client 2   │──┼──▶│   Center    │
│ (Router C+D)│  │   │   Server    │
└─────────────┘  │   └─────────────┘
                 │          │
┌─────────────┐  │          │
│  Client N   │──┘          ▼
│ (Router X+Y)│        Web Dashboard
└─────────────┘       (Visualizations)
```

## Configuration Reference

### Client (config.json)
```json
{
  "router1": {
    "gateway": "IP_ADDRESS",
    "interface": "INTERFACE_NAME"
  },
  "router2": {
    "gateway": "IP_ADDRESS",
    "interface": "INTERFACE_NAME"
  },
  "ping_target": "8.8.8.8",
  "ping_count": 20,
  "test_interval_seconds": 300,
  "results_dir": "/app/results",
  "center_server_url": "http://CENTER_SERVER_IP:5000",
  "heartbeat_interval_seconds": 60,
  "client_id": ""
}
```

**Parameters:**
- `heartbeat_interval_seconds`: How often to send heartbeat to center server (adjustable, default: 60)
- `client_id`: Unique identifier for this client (optional, defaults to hostname)

## Requirements

- Docker and Docker Compose
- For clients: Host network mode with multiple network interfaces
- For server: Port 5000 accessible from clients

## Future Enhancements

- [ ] Database backend for better performance
- [ ] Authentication and multi-user support
- [ ] Alert notifications (email, Slack, etc.)
- [ ] Historical data analysis and trends
- [ ] Data export (CSV, Excel)
- [ ] Mobile-responsive dashboard
- [ ] Comparison reports
- [ ] SLA tracking

## License

MIT
