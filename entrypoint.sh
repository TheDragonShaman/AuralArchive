#!/bin/bash
set -e

# Default to root if PUID/PGID not set
PUID=${PUID:-0}
PGID=${PGID:-0}

echo "-----------------------------------"
echo "AuralArchive Docker Entrypoint"
echo "-----------------------------------"
echo "PUID: ${PUID}"
echo "PGID: ${PGID}"
echo "-----------------------------------"

# If running as root (PUID=0), just run the app directly
if [ "$PUID" -eq 0 ]; then
    echo "Running as root (PUID=0)..."
    exec python /app/auralarchive/app.py
fi

# Create group if it doesn't exist
if ! getent group auralarchive >/dev/null 2>&1; then
    echo "Creating group 'auralarchive' with GID ${PGID}..."
    groupadd -g "${PGID}" auralarchive
else
    # Update existing group GID if needed
    EXISTING_GID=$(getent group auralarchive | cut -d: -f3)
    if [ "$EXISTING_GID" != "$PGID" ]; then
        echo "Updating group 'auralarchive' GID from ${EXISTING_GID} to ${PGID}..."
        groupmod -g "${PGID}" auralarchive
    fi
fi

# Create user if it doesn't exist
if ! id -u auralarchive >/dev/null 2>&1; then
    echo "Creating user 'auralarchive' with UID ${PUID}..."
    useradd -u "${PUID}" -g "${PGID}" -d /app -s /bin/bash auralarchive
else
    # Update existing user UID if needed
    EXISTING_UID=$(id -u auralarchive)
    if [ "$EXISTING_UID" != "$PUID" ]; then
        echo "Updating user 'auralarchive' UID from ${EXISTING_UID} to ${PUID}..."
        usermod -u "${PUID}" auralarchive
    fi
fi

# Ensure directories exist and have correct permissions
echo "Setting up directories..."
mkdir -p /config /downloads /import /app/auralarchive/logs /app/conversion /app/audible_dl

echo "Fixing permissions for volumes..."
# Only change ownership if the directory is writable (not a read-only mount)
if [ -w /config ]; then
    chown -R "${PUID}:${PGID}" /config
fi

if [ -w /downloads ]; then
    chown -R "${PUID}:${PGID}" /downloads
fi

if [ -w /import ]; then
    chown -R "${PUID}:${PGID}" /import
fi

# Fix app directory permissions (for logs, conversion, etc.)
chown -R "${PUID}:${PGID}" /app/auralarchive/logs 2>/dev/null || true
chown -R "${PUID}:${PGID}" /app/conversion 2>/dev/null || true
chown -R "${PUID}:${PGID}" /app/audible_dl 2>/dev/null || true

echo "Starting AuralArchive as user auralarchive (${PUID}:${PGID})..."
echo "-----------------------------------"

# Run as the specified user
exec gosu auralarchive python /app/auralarchive/app.py
