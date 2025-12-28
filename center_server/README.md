# Router Benchmark Center Server

A web-based dashboard for collecting and visualizing router benchmark logs from multiple client nodes, with secure remote command execution capabilities.

## Features

- **Log Collection**: REST API endpoint to receive benchmark data from clients
- **Client Monitoring**: Track active clients with heartbeat/keepalive mechanism
- **Per-Client Filtering**: View data from specific client or all clients combined
- **Real-time Visualization**: Interactive charts showing packet loss % and latency over time
- **Remote Command Execution**: Send whitelisted commands to clients with mutual authentication
- **Web Shell**: Real-time interactive terminal access to clients via WebSocket
- **Admin Authentication**: API key-based admin access
- **Audit Logging**: Complete audit trail of all command activity
- **Docker Deployment**: Easy deployment using Docker Compose
- **Persistent Storage**: Data stored in JSONL format

## Quick Start

### 1. Deploy the Center Server

```bash
cd center_server
docker-compose up -d
```

The server will be available at `http://localhost:5000`

### 2. Initialize Admin Account

```bash
curl -X POST http://localhost:5000/api/admin/init \
  -H "Content-Type: application/json" \
  -d '{"admin_name": "admin"}'
```

**Important:** Save the `api_key` returned - it cannot be retrieved later!

### 3. Register Clients

```bash
curl -X POST http://localhost:5000/api/clients/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"client_id": "benchmark-client-1"}'
```

**Important:** Save the `secret_key` returned - configure this on the client!

### 4. Configure Clients

Update the `config.json` on each benchmark client:

```json
{
  "center_server_url": "http://YOUR_SERVER_IP:5000",
  "client_id": "benchmark-client-1",
  "secret_key": "SECRET_KEY_FROM_REGISTRATION",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10
}
```

### 5. Access Dashboard

Open your browser and navigate to:
```
http://YOUR_SERVER_IP:5000
```

The dashboard has three tabs:
- **Monitoring**: Charts, statistics, and client status
- **Remote Commands**: Send commands and view results
- **Web Shell**: Interactive terminal access to clients

## API Reference

### Monitoring Endpoints

#### POST /api/logs
Receive benchmark logs from clients

**Request Body:**
```json
{
  "timestamp": "2025-12-07T10:00:00",
  "client_id": "client-001",
  "router1": {
    "router": "Router 1",
    "packet_loss_pct": 0.0,
    "avg_ms": 15.5
  },
  "router2": {
    "router": "Router 2",
    "packet_loss_pct": 0.0,
    "avg_ms": 18.2
  }
}
```

#### GET /api/data
Get benchmark data for visualization

**Query Parameters:**
- `limit` (optional): Number of recent records (default: 100)
- `client_id` (optional): Filter by specific client

#### GET /api/stats
Get summary statistics

**Query Parameters:**
- `client_id` (optional): Filter by specific client

#### POST /api/heartbeat
Receive heartbeat from clients

**Request Body:**
```json
{
  "client_id": "client-001",
  "hostname": "benchmark-host-1",
  "router1_interface": "eth0",
  "router2_interface": "eth1"
}
```

#### GET /api/clients
Get list of clients with their status

**Query Parameters:**
- `timeout` (optional): Seconds to consider client offline (default: 120)

#### GET /health
Health check endpoint

---

### Admin Management Endpoints

#### POST /api/admin/init
Initialize the first admin account (only works once)

**Request Body:**
```json
{"admin_name": "admin"}
```

**Response:**
```json
{
  "status": "success",
  "api_key": "YOUR_ADMIN_API_KEY",
  "admin_name": "admin"
}
```

#### POST /api/admin/create
Create additional admin accounts (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

**Request Body:**
```json
{"admin_name": "admin2"}
```

---

### Client Registration Endpoints

#### POST /api/clients/register
Register a new client (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

**Request Body:**
```json
{"client_id": "my-client"}
```

**Response:**
```json
{
  "status": "success",
  "client_id": "my-client",
  "secret_key": "CLIENT_SECRET_KEY"
}
```

#### GET /api/clients/registered
List all registered clients (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

#### POST /api/clients/{client_id}/revoke
Revoke a client's access (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

---

### Command Execution Endpoints

#### GET /api/commands/whitelist
Get list of available whitelisted commands (no auth required)

**Response:**
```json
{
  "commands": [
    {
      "id": "system_info",
      "description": "Get system kernel and OS info",
      "category": "system",
      "params": [],
      "timeout": 10
    }
  ],
  "total": 22
}
```

#### POST /api/commands/send
Queue a command for a client (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

**Request Body:**
```json
{
  "client_id": "benchmark-client-1",
  "command_id": "system_info",
  "params": {}
}
```

For commands with parameters:
```json
{
  "client_id": "benchmark-client-1",
  "command_id": "ping_test",
  "params": {
    "target": "8.8.8.8",
    "count": "4"
  }
}
```

#### GET /api/commands/pending/{client_id}
View pending commands for a client (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

#### POST /api/commands/pending/{client_id}/clear
Clear all pending commands for a client (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

#### GET /api/commands/poll
Client polls for pending commands (requires client auth)

**Headers:**
- `X-Client-ID: client-id`
- `X-Client-API-Key: secret-key`

#### POST /api/commands/result
Client submits command execution result (requires client auth)

**Headers:**
- `X-Client-ID: client-id`
- `X-Client-API-Key: secret-key`

**Request Body:**
```json
{
  "command_uuid": "...",
  "command_id": "system_info",
  "exit_code": 0,
  "stdout": "Linux hostname 5.4.0 ...",
  "stderr": "",
  "executed_at": "2025-12-07T10:00:00",
  "duration_seconds": 0.05
}
```

#### GET /api/commands/results
Get command execution results (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

**Query Parameters:**
- `client_id` (optional): Filter by client
- `limit` (optional): Max results (default: 100)

#### GET /api/commands/results/{command_uuid}
Get specific command result by UUID (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

#### GET /api/commands/audit
Get command audit log (requires admin auth)

**Headers:** `X-Admin-API-Key: YOUR_ADMIN_KEY`

**Query Parameters:**
- `limit` (optional): Max entries (default: 100)

---

## Available Commands

The whitelist includes these pre-approved commands:

### System Commands
| ID | Description |
|----|-------------|
| `system_info` | Get system kernel and OS info |
| `hostname` | Get machine hostname |
| `uptime` | Show system uptime and load |
| `disk_usage` | Show disk usage |
| `memory_info` | Show memory usage |
| `cpu_info` | Show CPU information |
| `process_list` | Top 20 processes by memory |
| `date_time` | Current date/time/timezone |

### Network Commands
| ID | Description | Parameters |
|----|-------------|------------|
| `network_interfaces` | List network interfaces | - |
| `routing_table` | Show routing table | - |
| `dns_config` | Show DNS configuration | - |
| `network_stats` | Network statistics | - |
| `ping_test` | Ping a host | `target` (IP), `count` (1-10) |
| `traceroute` | Trace route to host | `target` (IP) |
| `interface_stats` | Stats for interface | `interface` (name) |
| `connection_count` | Socket statistics | - |
| `arp_table` | Show ARP table | - |

### Docker Commands
| ID | Description |
|----|-------------|
| `docker_ps` | List running containers |
| `docker_stats` | Container resource usage |

### Benchmark Commands
| ID | Description |
|----|-------------|
| `benchmark_status` | Check if benchmark running |
| `benchmark_logs` | Show last 50 log lines |

See [REMOTE_COMMANDS_README.md](REMOTE_COMMANDS_README.md) for complete documentation.

---

## Data Storage

Data is stored in the `/app/data/` directory:

| File | Description |
|------|-------------|
| `benchmark_data.jsonl` | All benchmark results |
| `clients.json` | Client heartbeat registry |
| `admin_secrets.json` | Admin API keys (protected) |
| `client_secrets.json` | Client secret keys (protected) |
| `pending_commands.json` | Queued commands |
| `command_results.jsonl` | Execution results |
| `command_audit.jsonl` | Audit log |
| `used_nonces.json` | Replay prevention |

---

## Dashboard Features

### Monitoring Tab
- **Statistics Cards**: Total records, packet loss, latency (color-coded)
- **Active Clients Table**: Online/offline status, interfaces, last seen
- **Charts**: Packet loss and latency over time
- **Controls**: Client filter, time range selector, refresh button

### Remote Commands Tab
- **Admin Authentication**: Enter and save your admin API key
- **Send Command**: Select client, command, and parameters
- **Command Results**: Table of recent results with "View" button for details

### Web Shell Tab
- **Client Selector**: Choose an online client to connect to
- **Terminal**: Full xterm.js terminal emulator
- **Features**:
  - Real-time bidirectional communication via WebSocket
  - PTY-based shell on the client (full terminal features)
  - Terminal resize support
  - Session timeout after 30 minutes of inactivity
  - Maximum 3 concurrent sessions per client
  - Use Ctrl+C to interrupt, Ctrl+D to close

---

## Managing the Server

### View logs
```bash
docker-compose logs -f
```

### Stop the server
```bash
docker-compose down
```

### Restart the server
```bash
docker-compose restart
```

### Rebuild after code changes
```bash
docker-compose down
docker-compose up -d --build
```

### Clear all data
```bash
rm -rf data/*
docker-compose restart
```

---

## Network Configuration

The server listens on port 5000. Ensure:
1. Port 5000 is open in your firewall
2. Clients can reach the server IP on port 5000
3. For cloud hosting, allow inbound traffic on port 5000

---

## Troubleshooting

### Clients can't connect
- Check firewall rules
- Verify server IP in client config
- Check server is running: `docker-compose ps`
- Check server logs: `docker-compose logs`

### Authentication errors
- Verify admin API key is correct
- Verify client secret_key matches registration
- Check if client was revoked

### Commands not executing
- Verify client has `remote_commands_enabled: true`
- Verify client has correct `secret_key`
- Check client logs for signature verification errors
- Ensure server and client clocks are synchronized

### No data showing in dashboard
- Verify clients are sending data
- Check server received data: `cat data/benchmark_data.jsonl`
- Check browser console for errors

### Web Shell not connecting
- Verify client has `web_shell_enabled: true` in config.json
- Check that the client is shown as "online" in the dashboard
- Verify WebSocket connection in browser dev tools (Network tab)
- Check server logs for shell-related errors
- Ensure client has python-socketio installed
