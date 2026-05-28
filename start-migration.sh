#!/bin/sh
# filepath: /workspaces/twiki-confluence-migration/start-migration.sh

# Create logs directory if it doesn't exist
mkdir -p /app/logs

# Install tmux if not present (add to dockerfile instead)
# apk add --no-cache tmux

echo "Starting TWiki Migration Service..."
echo "Container is ready. Use 'docker exec' to connect."

# Start tmux session if it doesn't exist
if ! tmux has-session -t migration-session 2>/dev/null; then
    echo "Creating new tmux session 'migration-session'..."
    tmux new-session -d -s migration-session
fi

echo "Tmux session 'migration-session' is ready."
echo "To connect: docker exec -it twiki-migration-app tmux attach-session -t migration-session"
echo "To run migration: python main.py"

# Keep container running
exec tail -f /dev/null