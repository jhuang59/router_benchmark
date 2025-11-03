FROM python:3.11-slim

# Install Flask
RUN pip install --no-cache-dir flask

# Create app directory
WORKDIR /app

# Copy application files
COPY app.py /app/
COPY templates /app/templates/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Run the application
CMD ["python3", "-u", "app.py"]
