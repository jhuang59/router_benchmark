# Router Benchmark

A distributed system for benchmarking router performance across multiple locations with centralized visualization and remote command execution.

![img_v3_02sb_e11c695f-972b-42df-aeec-1226729d3deg](https://github.com/user-attachments/assets/158a64e6-0030-4b34-98a3-5e18c2688ce7)

## Architecture

This project consists of two stages:

### Stage 1: Benchmark Clients
- **Location**: Deploy on machines with multiple network interfaces connected to different routers
- **Function**: Continuously ping a target through different routers and collect performance metrics
- **Output**: Local JSON logs + sends data to center server
- **Remote Commands**: Execute whitelisted commands from center server (with mutual authentication)

### Stage 2: Center Server
- **Location**: Deploy on a central server (cloud or local)
- **Function**: Collects logs from all benchmark clients and provides web-based visualization
- **Features**: Real-time dashboard, remote command execution, client management

## Quick Start

### Deploy Center Server (Stage 2)

1. On your central server:
```bash
cd center_server
docker-compose up -d
```

2. Initialize admin account:
```bash
curl -X POST http://localhost:5000/api/admin/init \
  -H "Content-Type: application/json" \
  -d '{"admin_name": "admin"}'
```
**Save the API key returned - you'll need it!**

3. Access dashboard at `http://YOUR_SERVER_IP:5000`

See [center_server/README.md](center_server/README.md) for detailed documentation.

### Deploy Benchmark Clients (Stage 1)

1. Register the client on the server (using admin API key):
```bash
curl -X POST http://YOUR_SERVER_IP:5000/api/clients/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_KEY" \
  -d '{"client_id": "my-client"}'
```
**Save the secret_key returned!**

2. On each client machine, update `config.json`:
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
  "center_server_url": "http://YOUR_CENTER_SERVER_IP:5000",
  "client_id": "my-client",
  "secret_key": "YOUR_SECRET_KEY_FROM_REGISTRATION",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10
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
- **Remote command execution** with signature verification
- **Web Shell server**: PTY-based shell access for remote terminal

### Server Features
- REST API for log collection
- Client monitoring with heartbeat tracking
- Active clients list showing online/offline status
- **Per-client data filtering**: View specific client or all clients
- Web-based dashboard with three tabs:
  - **Monitoring**: Real-time charts and statistics
  - **Remote Commands**: Send commands and view results
  - **Web Shell**: Interactive terminal access to clients
- **Mutual authentication**: HMAC-SHA256 signed commands
- **Command whitelist**: Only pre-approved commands can be executed
- **Web Shell**: Real-time terminal access via WebSocket
- **Audit logging**: All command activity is logged
- Auto-refresh dashboard
- Configurable time ranges

## Security Features

### Mutual Authentication
- **Client → Server**: API key authentication
- **Server → Client**: Commands are HMAC-SHA256 signed
- **Replay protection**: Timestamp + nonce validation
- **Whitelist-only execution**: Only pre-approved commands run

```
Admin Dashboard              Center Server                   Client
     │                            │                            │
     │ 1. Send command            │                            │
     │ (with admin API key)       │                            │
     │───────────────────────────▶│                            │
     │                            │ 2. Sign command with       │
     │                            │    client's secret_key     │
     │                            │                            │
     │                            │◀───────────────────────────│
     │                            │ 3. Client polls            │
     │                            │    (with API key)          │
     │                            │                            │
     │                            │ 4. Return signed command   │
     │                            │───────────────────────────▶│
     │                            │                            │
     │                            │    5. VERIFY SIGNATURE     │
     │                            │    before execution!       │
     │                            │                            │
     │                            │◀───────────────────────────│
     │                            │ 6. Submit result           │
```

## Use Cases

1. **Multi-Location Network Monitoring**: Deploy clients in different offices/locations
2. **ISP Comparison**: Compare performance across different internet providers
3. **Failover Testing**: Monitor primary and backup connections
4. **Network Quality Analysis**: Track network performance over time
5. **Remote Diagnostics**: Run system commands on remote clients

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
                      + Remote Commands
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
  "client_id": "",
  "secret_key": "",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10,
  "web_shell_enabled": true
}
```

**Parameters:**
| Parameter | Description | Default |
|-----------|-------------|---------|
| `heartbeat_interval_seconds` | How often to send heartbeat to center server | 60 |
| `client_id` | Unique identifier for this client | hostname |
| `secret_key` | Shared secret for command authentication | "" |
| `remote_commands_enabled` | Enable/disable remote command execution | true |
| `command_poll_interval_seconds` | How often to poll for commands | 10 |
| `web_shell_enabled` | Enable/disable web shell access | true |

## Requirements

- Docker and Docker Compose
- For clients: Host network mode with multiple network interfaces
- For server: Port 5000 accessible from clients

## Documentation

- [Center Server Documentation](center_server/README.md) - API reference and server setup
- [Remote Commands Guide](center_server/REMOTE_COMMANDS_README.md) - Complete remote execution guide
- [Deployment Guide](deployment_readme.md) - Step-by-step deployment instructions

## License

MIT
