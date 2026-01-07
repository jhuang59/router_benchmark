FROM python:3.11-slim

# Create app directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py /app/
COPY auth.py /app/
COPY commands.py /app/
COPY shell_manager.py /app/
COPY ai_diagnostics.py /app/
COPY command_whitelist.json /app/
COPY templates /app/templates/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Run the application with gevent for WebSocket support
CMD ["python3", "-u", "app.py"]
