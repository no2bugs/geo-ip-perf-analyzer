FROM python:3.9-slim

# Install system dependencies (ping, openvpn, speedtest, networking tools)
RUN apt-get update && apt-get install -y \
    curl \
    iputils-ping \
    jq \
    openvpn \
    sudo \
    iproute2 \
    psmisc \
    && rm -rf /var/lib/apt/lists/*

# Allow all users to use sudo without password (needed for OpenVPN)
RUN echo "ALL ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV SERVERS_FILE=/data/servers.list
ENV RESULTS_FILE=/data/results.json
ENV GEOIP_CITY=/data/GeoLite2-City.mmdb
ENV GEOIP_COUNTRY=/data/GeoLite2-Country.mmdb

# Expose port
EXPOSE 5000

# Run with Gunicorn
# 2 workers: one handles web requests, the other can run scans without blocking the UI.
# Scan state is shared via /tmp file for cross-worker access.
# threads=4 per worker for concurrent request handling.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "600", "web.app:app"]
