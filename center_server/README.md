# Router Benchmark Center Server

A simple web-based dashboard for collecting and visualizing router benchmark logs from multiple client nodes.

## Features

- **Log Collection**: REST API endpoint to receive benchmark data from clients
- **Client Monitoring**: Track active clients with heartbeat/keepalive mechanism
- **Per-Client Filtering**: View data from specific client or all clients combined
- **Real-time Visualization**: Interactive charts showing packet loss % and latency over time
- **Client List**: View all connected clients with online/offline status
- **Simple Dashboard**: Clean web UI with stats cards and time-series charts
- **Docker Deployment**: Easy deployment using Docker Compose
- **Persistent Storage**: Data stored in JSONL format with client identification

## Quick Start

### 1. Deploy the Center Server

```bash
cd center_server
docker-compose up -d
```

The server will be available at `http://localhost:5000`

### 2. Configure Clients

Update the `config.json` on each benchmark client:

```json
{
  ...
  "center_server_url": "http://YOUR_SERVER_IP:5000"
}
```

Replace `YOUR_SERVER_IP` with the actual IP address of the server running the center server.

### 3. Access Dashboard

Open your browser and navigate to:
```
http://YOUR_SERVER_IP:5000
```

You'll see:
- Live statistics for both routers
- Active clients list with online/offline status
- Client filter dropdown to view specific client or all clients
- Packet loss % over time chart (per-client or aggregated)
- Average latency over time chart (per-client or aggregated)
- Auto-refresh every 30 seconds

### 4. Filter by Client (Optional)

Use the "View Client" dropdown to:
- View **All Clients**: See aggregated data from all clients
- View **Specific Client**: Filter to show only one client's performance data

Charts automatically update to show selected client's data.

## API Endpoints

### POST /api/logs
Receive benchmark logs from clients

**Request Body:**
```json
{
  "timestamp": "2025-11-03T10:00:00",
  "router1": {
    "router": "Router 1",
    "packet_loss_pct": 0.0,
    "avg_ms": 15.5,
    ...
  },
  "router2": {
    "router": "Router 2",
    "packet_loss_pct": 0.0,
    "avg_ms": 18.2,
    ...
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Log received"
}
```

### GET /api/data
Get benchmark data for visualization

**Query Parameters:**
- `limit` (optional): Number of recent records to return (default: 100)
- `client_id` (optional): Filter by specific client (default: all clients)

**Response:**
```json
{
  "data": [...],
  "total": 150
}
```

**Examples:**
- All clients: `GET /api/data?limit=100`
- Specific client: `GET /api/data?limit=100&client_id=office-client-1`

### GET /api/stats
Get summary statistics

**Query Parameters:**
- `client_id` (optional): Filter by specific client (default: all clients)

**Response:**
```json
{
  "stats": {
    "total_records": 150,
    "latest_timestamp": "2025-11-03T10:00:00",
    "client_id": "office-client-1",
    "hostname": "benchmark-host-1",
    "router1_latest_loss": 0.0,
    "router2_latest_loss": 0.0,
    "router1_latest_avg_ms": 15.5,
    "router2_latest_avg_ms": 18.2
  }
}
```

### POST /api/heartbeat
Receive heartbeat/keepalive from clients

**Request Body:**
```json
{
  "client_id": "client-001",
  "hostname": "benchmark-host-1",
  "router1_interface": "enp0s31f6",
  "router2_interface": "enp8s0f0"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Heartbeat received"
}
```

### GET /api/clients
Get list of active clients with their status

**Query Parameters:**
- `timeout` (optional): Seconds to consider client offline (default: 120)

**Response:**
```json
{
  "clients": [
    {
      "client_id": "client-001",
      "hostname": "benchmark-host-1",
      "last_heartbeat": "2025-11-03T10:00:00",
      "seconds_since_heartbeat": 15,
      "status": "online",
      "router1_interface": "enp0s31f6",
      "router2_interface": "enp8s0f0"
    }
  ],
  "total": 1,
  "online": 1,
  "offline": 0
}
```

### GET /health
Health check endpoint

## Data Storage

Data is stored in the `/app/data/` directory (inside the container):
- **benchmark_data.jsonl**: All benchmark results (one JSON object per line)
- **clients.json**: Registry of all clients and their last heartbeat times

On the host, this maps to `./data/` (relative to center_server directory).

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

### Clear all data
```bash
rm -f data/benchmark_data.jsonl
docker-compose restart
```

## Dashboard Features

### Statistics Cards
- Total records collected
- Latest packet loss % for each router (color-coded: green = 0%, yellow < 5%, red ≥ 5%)
- Latest average latency for each router (color-coded: green < 50ms, yellow < 100ms, red ≥ 100ms)

### Active Clients
- Table showing all clients that have sent heartbeats
- Client ID, hostname, and network interfaces
- Online/offline status with color coding
- Last seen time (e.g., "15s ago", "5m ago")
- Clients are marked offline after 2 minutes without heartbeat

### Charts
- **Packet Loss Over Time**: Line chart showing loss % for both routers
- **Latency Over Time**: Line chart showing average latency for both routers

### Controls
- **Client Filter**: Dropdown to view specific client or all clients
  - Select "All Clients" to see aggregated data
  - Select specific client to see only that client's data
  - Charts and stats update automatically when selection changes
- **Time Range**: Selector for number of records (Last 50/100/200/500 records)
- **Manual Refresh**: Button to update dashboard immediately
- **Auto-refresh**: Updates every 30 seconds automatically

## Network Configuration

The server listens on port 5000. Make sure:
1. Port 5000 is open in your firewall
2. Clients can reach the server IP on port 5000
3. If using cloud hosting, ensure security groups allow inbound traffic on port 5000

## Extending the Server

This is designed to be simple and extensible. Future enhancements could include:

- Database backend (PostgreSQL, InfluxDB)
- Authentication and multi-tenancy
- Alerting when packet loss exceeds threshold
- Historical data analysis and trends
- Export data as CSV
- Comparison views and reports

## Troubleshooting

### Clients can't connect
- Check firewall rules
- Verify server IP is correct in client config
- Check server is running: `docker-compose ps`
- Check server logs: `docker-compose logs`

### No data showing in dashboard
- Verify clients are sending data (check client logs)
- Check server received data: `cat data/benchmark_data.jsonl`
- Check browser console for errors

### Charts not updating
- Check browser console for errors
- Verify API endpoints work: `curl http://localhost:5000/api/stats`
- Hard refresh browser (Ctrl+F5)
