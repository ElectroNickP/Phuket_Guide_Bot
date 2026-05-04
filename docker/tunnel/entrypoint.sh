#!/bin/bash

LOG_FILE="/app/shared/tunnel.log"
URL_FILE="/app/shared/tunnel_url.txt"

mkdir -p /app/shared
# Clear previous run data
> $LOG_FILE
rm -f $URL_FILE

echo "Starting cloudflared tunnel monitor..."

# Function to run cloudflared
run_tunnel() {
    echo "Launching cloudflared..."
    cloudflared tunnel --no-autoupdate --url http://bot:8080 >> $LOG_FILE 2>&1
}

# Start tunnel in background and restart if it crashes
(
    while true; do
        run_tunnel
        echo "cloudflared exited. Restarting in 10 seconds..."
        sleep 10
    done
) &

# Monitor the log file for the URL
while true; do
    # Regex improvement: 
    # 1. Look for the specific "Your quick Tunnel has been created" line or similar if possible, 
    #    but standard grep on the whole log is fine if we exclude 'api.'
    # 2. Exclude api.trycloudflare.com by requiring at least one character that isn't 'api' 
    #    or just using a negative lookahead if grep supports it (it doesn't usually in basic mode).
    #    Let's just grep and then grep -v 'api.trycloudflare.com'
    
    URL=$(grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" $LOG_FILE | grep -v "api.trycloudflare.com" | tail -n 1)
    
    if [ ! -z "$URL" ]; then
        if [ "$URL" != "$(cat $URL_FILE 2>/dev/null)" ]; then
            echo "$URL" > $URL_FILE
            echo "Found Tunnel URL: $URL"
        fi
    fi
    sleep 10
done
