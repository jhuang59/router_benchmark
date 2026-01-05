# EdgePulse - Edge Device Monitor

A distributed monitoring and diagnostics platform that deploys containerized agents to edge devices for real-time health tracking, remote command execution, and interactive shell access through a centralized web dashboard.

![Dashboard](https://github.com/user-attachments/assets/158a64e6-0030-4b34-98a3-5e18c2688ce7)

## Overview

EdgePulse consists of two components:

| Component | Description |
|-----------|-------------|
| **Center Server** | Central hub that collects data, provides web dashboard, and coordinates remote commands |
| **Client Agent** | Deployed on edge devices to monitor network health and execute remote commands |

---

## Quick Start

### Step 1: Deploy Center Server

```bash
cd center_server
docker-compose up -d --build
```

### Step 2: Initialize Admin Account

```bash
curl -X POST http://localhost:5000/api/admin/init \
  -H "Content-Type: application/json" \
  -d '{"admin_name": "admin"}'
```

**Important:** Save the `api_key` from the response - you'll need it!

Example response:
```json
{
  "status": "success",
  "api_key": "abc123xyz...",
  "admin_name": "admin"
}
```

### Step 3: Register a Client

```bash
curl -X POST http://localhost:5000/api/clients/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"client_id": "jetbot-01"}'
```

**Important:** Save the `secret_key` from the response!

Example response:
```json
{
  "status": "success",
  "client_id": "jetbot-01",
  "secret_key": "xyz789abc..."
}
```

### Step 4: Configure and Deploy Client

1. Edit `config.json` on the client machine:

```json
{
  "router1": {
    "gateway": "192.168.1.1",
    "interface": "eth0"
  },
  "router2": {
    "gateway": "192.168.30.1",
    "interface": "wlan0"
  },
  "ping_target": "8.8.8.8",
  "ping_count": 20,
  "test_interval_seconds": 300,
  "center_server_url": "http://YOUR_SERVER_IP:5000",
  "client_id": "jetbot-01",
  "secret_key": "YOUR_SECRET_KEY_FROM_STEP_3",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10,
  "web_shell_enabled": true
}
```

2. Deploy the client using one of the options below:

#### Option A: Native Deployment (Recommended for Web Shell)

Run the client directly on the host system for full host access via Web Shell:

```bash
# Install dependencies
pip3 install requests python-socketio websocket-client

# Run the client
python3 ping_benchmark.py
```

**Pros:**
- Web Shell connects directly to host system
- Full access to host filesystem, processes, and hardware
- No container isolation overhead

**Cons:**
- Requires Python 3 and dependencies installed on host
- Less isolated from host system

#### Option B: Docker Deployment

Run the client in a container for isolation:

```bash
docker-compose up -d --build
```

**Pros:**
- Isolated environment
- Easy deployment and updates
- Consistent across different host systems

**Cons:**
- Web Shell connects to container environment, not host
- Limited access to host resources

### Step 5: Access Dashboard

Open your browser: `http://YOUR_SERVER_IP:5000`

---

## Center Server Configuration

### Docker Compose (center_server/docker-compose.yml)

```yaml
version: '3.8'
services:
  center-server:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Directory for persistent data | `/app/data` |

### Data Files

| File | Description |
|------|-------------|
| `data/benchmark_data.jsonl` | Collected benchmark results |
| `data/clients.json` | Client heartbeat registry |
| `data/admin_secrets.json` | Admin API keys |
| `data/client_secrets.json` | Client secret keys |
| `data/pending_commands.json` | Queued commands |
| `data/command_results.jsonl` | Command execution results |
| `data/command_audit.jsonl` | Audit log |

---

## Client Configuration

### config.json Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `router1.gateway` | Primary router gateway IP | - | Yes |
| `router1.interface` | Primary network interface | - | Yes |
| `router2.gateway` | Secondary router gateway IP | - | Yes |
| `router2.interface` | Secondary network interface | - | Yes |
| `ping_target` | Target IP for ping tests | `8.8.8.8` | No |
| `ping_count` | Number of pings per test | `20` | No |
| `test_interval_seconds` | Seconds between tests | `300` | No |
| `center_server_url` | Center server URL | - | Yes |
| `client_id` | Unique client identifier | hostname | No |
| `secret_key` | Client authentication key | - | Yes* |
| `remote_commands_enabled` | Enable remote commands | `true` | No |
| `command_poll_interval_seconds` | Command poll interval | `10` | No |
| `web_shell_enabled` | Enable web shell access | `true` | No |

*Required for remote commands and web shell

### Example Configurations

**Minimal Configuration (monitoring only):**
```json
{
  "router1": { "gateway": "192.168.1.1", "interface": "eth0" },
  "router2": { "gateway": "192.168.2.1", "interface": "eth1" },
  "center_server_url": "http://192.168.1.100:5000",
  "client_id": "office-monitor"
}
```

**Full Configuration (all features):**
```json
{
  "router1": { "gateway": "192.168.1.1", "interface": "eth0" },
  "router2": { "gateway": "192.168.2.1", "interface": "wlan0" },
  "ping_target": "8.8.8.8",
  "ping_count": 20,
  "test_interval_seconds": 300,
  "center_server_url": "http://192.168.1.100:5000",
  "heartbeat_interval_seconds": 60,
  "client_id": "jetbot-01",
  "secret_key": "your-secret-key-here",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10,
  "web_shell_enabled": true
}
```

---

## Using the Dashboard

### Tab 1: Monitoring

View real-time network performance metrics:

- **Statistics Cards**: Total records, packet loss %, latency
- **Active Clients Table**: Online/offline status, last seen
- **Charts**: Packet loss and latency over time
- **Filters**: Select specific client, adjust time range

### Tab 2: Remote Commands

Execute pre-approved commands on remote clients:

1. **Enter Admin API Key**: Paste your admin key and click "Save Key"
2. **Select Target Client**: Choose a client from the dropdown
3. **Select Command**: Pick a command from the whitelist
4. **Fill Parameters**: Enter required parameters (if any)
5. **Send**: Click "Send Command"
6. **View Results**: Check the results table below

**Available Commands:**

| Category | Commands |
|----------|----------|
| System | `system_info`, `hostname`, `uptime`, `disk_usage`, `memory_info`, `cpu_info`, `process_list`, `date_time`, `load_average`, `top_cpu`, `dmesg_errors`, `systemd_failed`, `disk_inodes` |
| Network | `network_interfaces`, `routing_table`, `dns_config`, `network_stats`, `ping_test`, `traceroute`, `interface_stats`, `connection_count`, `arp_table`, `listening_ports` |
| Docker | `docker_ps`, `docker_stats` |
| Benchmark | `benchmark_status`, `benchmark_logs` |

### Tab 3: Web Shell

Open an interactive terminal session to remote clients:

1. **Save Admin API Key** (in Remote Commands tab first)
2. **Go to Web Shell tab**
3. **Select a client** from the dropdown (only online clients shown)
4. **Click "Connect"** to start the session
5. **Use the terminal** - type commands as you would in SSH
6. **Click "Disconnect"** or press Ctrl+D to close

**Web Shell Features:**
- Full PTY terminal with color support
- Terminal resize support
- 30-minute session timeout
- Maximum 3 concurrent sessions per client

**Important:** The Web Shell connects to the environment where the client agent runs:
- **Native deployment**: Shell connects to the host system (full access)
- **Docker deployment**: Shell connects to the container (limited to container environment)

### Tab 4: AI Troubleshoot

AI-powered diagnostics to automatically analyze edge device health:

1. **Configure AI** (first time only):
   - Enter your OpenAI or Anthropic API key in the configuration section
   - Or set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` environment variable

2. **Select Target Client**: Choose an online client to diagnose

3. **Select Categories**: Check which areas to analyze:
   - System (CPU, memory, processes, services)
   - Disk (usage, inodes)
   - Network (interfaces, routes, connections)
   - Docker (container status)
   - Benchmark (client status)

4. **Optional Question**: Ask a specific question like "Why is CPU usage high?"

5. **Run Diagnosis**: Click the button to:
   - Automatically collect diagnostic data from the client
   - Send data to AI for analysis
   - Receive structured recommendations

**AI Diagnosis Output:**
- Health Summary (HEALTHY, WARNING, or CRITICAL)
- Issues Found with severity indicators
- Root Cause Analysis
- Actionable Recommendations
- Ready-to-run fix commands

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Client 1       │     │   Client 2       │     │   Client N       │
│  (Jetson Nano)   │     │  (Raspberry Pi)  │     │  (Edge Device)   │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │ HTTP/WebSocket         │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │     Center Server       │
                    │                         │
                    │  • REST API             │
                    │  • WebSocket Server     │
                    │  • Web Dashboard        │
                    │  • Command Queue        │
                    └─────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │    Admin Dashboard      │
                    │                         │
                    │  • Monitoring           │
                    │  • Remote Commands      │
                    │  • Web Shell            │
                    │  • AI Troubleshoot      │
                    └─────────────────────────┘
```

---

## Security

### Authentication Flow

```
Admin Dashboard              Center Server                   Client
     │                            │                            │
     │ 1. Send command            │                            │
     │ (with admin API key)       │                            │
     │───────────────────────────▶│                            │
     │                            │                            │
     │                            │◀───────────────────────────│
     │                            │ 2. Client polls            │
     │                            │    (with client API key)   │
     │                            │                            │
     │                            │ 3. Return command          │
     │                            │───────────────────────────▶│
     │                            │                            │
     │                            │    4. Execute command      │
     │                            │                            │
     │                            │◀───────────────────────────│
     │                            │ 5. Submit result           │
```

### Security Features

- **Admin API Key**: Required for all administrative actions
- **Client API Key**: Unique secret for each client
- **Command Whitelist**: Only pre-approved commands can execute
- **Audit Logging**: All command activity is logged

---

## Troubleshooting

### Client not showing in dashboard

1. Check client logs: `docker-compose logs -f`
2. Verify `center_server_url` is correct
3. Ensure port 5000 is accessible from client
4. Check server logs: `docker-compose logs -f` (in center_server/)

### Remote commands not working

1. Verify `remote_commands_enabled: true` in config.json
2. Verify `secret_key` matches the registered key
3. Check client is online in dashboard

### Web shell not connecting

1. Save Admin API Key in Remote Commands tab first
2. Verify `web_shell_enabled: true` in config.json
3. Check client is online (green status)
4. Check browser console for WebSocket errors

### Web shell connects to container instead of host

This is expected behavior when using Docker deployment. To access the host system:

1. **Switch to native deployment** (recommended):
   ```bash
   # Stop Docker container
   docker-compose down

   # Run client natively
   pip3 install requests python-socketio websocket-client
   python3 ping_benchmark.py
   ```

2. The Web Shell will now connect directly to the host system

### Authentication errors

1. Verify admin API key is correct
2. For clients, verify `secret_key` matches registration
3. Check if client was revoked

---

## Example Deployment: JetBot

Deployed on an enhanced JetBot kit (Jetson Nano + SIM7600G-H 4G/GPS module) to monitor robot health metrics remotely over cellular networks.

**config.json for JetBot:**
```json
{
  "router1": { "gateway": "192.168.55.1", "interface": "usb0" },
  "router2": { "gateway": "192.168.1.1", "interface": "wlan0" },
  "ping_target": "8.8.8.8",
  "center_server_url": "http://your-server.com:5000",
  "client_id": "jetbot-01",
  "secret_key": "your-secret-key",
  "remote_commands_enabled": true,
  "web_shell_enabled": true
}
```

---

## Documentation

- [Center Server API Reference](center_server/README.md)
- [Remote Commands Guide](center_server/REMOTE_COMMANDS_README.md)

## License

MIT
