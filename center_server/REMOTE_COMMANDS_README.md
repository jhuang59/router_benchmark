# Remote Command Execution

This feature allows the center server to send commands to client machines for remote execution. Commands are executed securely with mutual authentication and are restricted to a whitelist of safe commands.

## Security Architecture

### Mutual Authentication

The system uses **mutual authentication** to prevent both unauthorized access and server impersonation:

1. **Client → Server Authentication**: Client presents API key to prove identity
2. **Server → Client Authentication**: Commands are signed with HMAC-SHA256, client verifies before execution

```
┌─────────────────┐                    ┌─────────────────┐
│  Center Server  │                    │     Client      │
│                 │                    │                 │
│ Has: secret_key │                    │ Has: secret_key │
│      (shared)   │                    │      (shared)   │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         │  Command + HMAC(command, secret_key) │
         │─────────────────────────────────────▶│
         │                                      │
         │                      Verify HMAC ────┤
         │                      before execute  │
         │                                      │
```

### Replay Attack Prevention

- **Timestamp validation**: Commands expire after 5 minutes
- **Nonce tracking**: Each command has a unique nonce; duplicates are rejected

### Command Whitelist

Only pre-approved commands can be executed. The whitelist is defined in `command_whitelist.json`.

---

## Quick Start

### Step 1: Initialize Admin Account

First, create an admin account (only works once):

```bash
curl -X POST http://localhost:5000/api/admin/init \
  -H "Content-Type: application/json" \
  -d '{"admin_name": "admin"}'
```

Response:
```json
{
  "status": "success",
  "message": "Admin account created. SAVE THIS API KEY - it cannot be retrieved later!",
  "api_key": "a1b2c3d4e5f6...",
  "admin_name": "admin"
}
```

**IMPORTANT**: Save the `api_key` - it cannot be retrieved later!

### Step 2: Register a Client

Use your admin API key to register a client:

```bash
curl -X POST http://localhost:5000/api/clients/register \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{"client_id": "benchmark-client-1"}'
```

Response:
```json
{
  "status": "success",
  "message": "Client registered. SAVE THIS SECRET KEY - it cannot be retrieved later!",
  "client_id": "benchmark-client-1",
  "secret_key": "x1y2z3..."
}
```

**IMPORTANT**: Save the `secret_key` - you need to configure this on the client!

### Step 3: Configure the Client

Edit the client's `config.json`:

```json
{
  "router1": { ... },
  "router2": { ... },
  "center_server_url": "http://YOUR_SERVER_IP:5000",
  "client_id": "benchmark-client-1",

  "secret_key": "x1y2z3...",
  "remote_commands_enabled": true,
  "command_poll_interval_seconds": 10
}
```

### Step 4: Start the Client

```bash
python3 ping_benchmark.py
```

You should see:
```
Remote commands: ENABLED (poll interval: 10s)
Command polling started for client: benchmark-client-1
```

### Step 5: Send a Command

List available commands:
```bash
curl http://localhost:5000/api/commands/whitelist
```

Send a command to a client:
```bash
curl -X POST http://localhost:5000/api/commands/send \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{
    "client_id": "benchmark-client-1",
    "command_id": "system_info",
    "params": {}
  }'
```

### Step 6: View Results

Get command results:
```bash
curl http://localhost:5000/api/commands/results \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY"
```

---

## API Reference

### Admin Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/admin/init` | POST | None | Initialize first admin (one-time) |
| `/api/admin/create` | POST | Admin | Create additional admin accounts |

### Client Management

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/clients/register` | POST | Admin | Register a new client |
| `/api/clients/registered` | GET | Admin | List all registered clients |
| `/api/clients/<id>/revoke` | POST | Admin | Revoke a client's access |

### Command Management

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/commands/whitelist` | GET | None | List available commands |
| `/api/commands/send` | POST | Admin | Queue a command for a client |
| `/api/commands/pending/<id>` | GET | Admin | View pending commands for client |
| `/api/commands/pending/<id>/clear` | POST | Admin | Clear pending commands |
| `/api/commands/results` | GET | Admin | Get command execution results |
| `/api/commands/results/<uuid>` | GET | Admin | Get specific result by UUID |
| `/api/commands/audit` | GET | Admin | View command audit log |

### Client Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/commands/poll` | GET | Client | Poll for pending commands |
| `/api/commands/result` | POST | Client | Submit command result |

---

## Available Commands

The default whitelist includes these safe commands:

### System Commands

| Command ID | Description |
|------------|-------------|
| `system_info` | Get system kernel and OS info (`uname -a`) |
| `hostname` | Get machine hostname |
| `uptime` | Show system uptime and load |
| `disk_usage` | Show disk usage (`df -h`) |
| `memory_info` | Show memory usage (`free -m`) |
| `cpu_info` | Show CPU information |
| `process_list` | Top 20 processes by memory |
| `date_time` | Current date, time, timezone |

### Network Commands

| Command ID | Description | Parameters |
|------------|-------------|------------|
| `network_interfaces` | List network interfaces | - |
| `routing_table` | Show routing table | - |
| `dns_config` | Show DNS configuration | - |
| `network_stats` | Network statistics | - |
| `ping_test` | Ping a host | `target` (IP), `count` (1-10) |
| `traceroute` | Trace route to host | `target` (IP) |
| `interface_stats` | Stats for an interface | `interface` (name) |
| `connection_count` | Socket statistics | - |
| `arp_table` | Show ARP table | - |

### Docker Commands

| Command ID | Description |
|------------|-------------|
| `docker_ps` | List running containers |
| `docker_stats` | Container resource usage |

### Benchmark Commands

| Command ID | Description |
|------------|-------------|
| `benchmark_status` | Check if benchmark is running |
| `benchmark_logs` | Show last 50 log lines |

---

## Sending Commands with Parameters

Some commands accept parameters. Example:

```bash
# Ping test with parameters
curl -X POST http://localhost:5000/api/commands/send \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{
    "client_id": "benchmark-client-1",
    "command_id": "ping_test",
    "params": {
      "target": "8.8.8.8",
      "count": "4"
    }
  }'

# Traceroute
curl -X POST http://localhost:5000/api/commands/send \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{
    "client_id": "benchmark-client-1",
    "command_id": "traceroute",
    "params": {
      "target": "1.1.1.1"
    }
  }'

# Interface stats
curl -X POST http://localhost:5000/api/commands/send \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: YOUR_ADMIN_API_KEY" \
  -d '{
    "client_id": "benchmark-client-1",
    "command_id": "interface_stats",
    "params": {
      "interface": "eth0"
    }
  }'
```

---

## Adding Custom Commands

Edit `command_whitelist.json` to add new commands:

```json
{
  "commands": {
    "my_custom_command": {
      "cmd": "echo 'Hello {name}'",
      "description": "A custom greeting command",
      "category": "custom",
      "params": ["name"],
      "param_validators": {
        "name": {
          "type": "hostname",
          "description": "Name to greet (alphanumeric only)"
        }
      },
      "timeout": 10
    }
  }
}
```

### Parameter Validators

| Type | Description |
|------|-------------|
| `ip` | Valid IPv4 address |
| `hostname` | Alphanumeric with hyphens/dots |
| `integer` | Integer with optional `min`/`max` |
| `choice` | Must be one of `choices` array |
| `path` | Safe relative path (no `..` or `/`) |

---

## Security Best Practices

1. **Protect API Keys**: Store admin and client API keys securely
2. **Use HTTPS**: In production, always use HTTPS to encrypt traffic
3. **Limit Whitelist**: Only add commands that are truly necessary
4. **Review Audit Logs**: Regularly check `/api/commands/audit`
5. **Revoke Compromised Keys**: Use `/api/clients/<id>/revoke` if a key is compromised
6. **Network Segmentation**: Limit which networks can access the server

---

## Troubleshooting

### Client shows "Remote commands: DISABLED"

- Check that `secret_key` is set in `config.json`
- Check that `remote_commands_enabled` is `true`

### Command rejected with "Invalid signature"

- Ensure the client's `secret_key` matches the one from registration
- Check that server and client clocks are synchronized (within 5 minutes)

### Command rejected with "Nonce already used"

- This indicates a replay attack was detected
- If legitimate, wait a few seconds and try again

### Client shows "Authentication failed"

- Verify `client_id` matches the registered name
- Verify `secret_key` is correct
- Check if the client was revoked

---

## Data Files

The server stores data in these files:

| File | Description |
|------|-------------|
| `data/admin_secrets.json` | Admin API keys (protected) |
| `data/client_secrets.json` | Client secret keys (protected) |
| `data/pending_commands.json` | Queued commands waiting for clients |
| `data/command_results.jsonl` | Execution results |
| `data/command_audit.jsonl` | Audit log of all command activity |
| `data/used_nonces.json` | Nonces for replay prevention |
