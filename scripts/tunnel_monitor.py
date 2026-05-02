import subprocess
import re
import time
import os

def get_tunnel_url():
    print("Searching for tunnel URL in logs...")
    # Give it a few seconds to start up if just launched
    for i in range(20):
        result = subprocess.run(["docker", "compose", "logs", "tunnel"], capture_output=True, text=True)
        # Look for https://*.trycloudflare.com
        # Logs usually look like: INF |  https://cradle-dirt-steam-burns.trycloudflare.com
        match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', result.stdout + result.stderr)
        if match:
            return match.group(0)
        if i % 5 == 0:
            print(f"Still waiting... ({i*2}s)")
        time.sleep(2)
    return None

def update_env(url):
    env_path = ".env"
    if not os.path.exists(env_path):
        print(f"Error: {env_path} not found")
        return False
    
    with open(env_path, "r") as f:
        content = f.read()
    
    if "WEBAPP_URL=" in content:
        # Replace existing
        new_content = re.sub(r'WEBAPP_URL=.*', f'WEBAPP_URL={url}', content)
    else:
        # Append new
        new_content = content + f"\nWEBAPP_URL={url}\n"
    
    with open(env_path, "w") as f:
        f.write(new_content)
    
    print(f"Successfully updated .env with: {url}")
    return True

def restart_bot():
    print("Restarting bot container to apply new URL...")
    subprocess.run(["docker", "compose", "restart", "bot"])

if __name__ == "__main__":
    url = get_tunnel_url()
    if url:
        print(f"Found tunnel URL: {url}")
        if update_env(url):
            restart_bot()
            print("✨ Professional fix complete! The bot is now using the new tunnel URL.")
    else:
        print("❌ Could not find tunnel URL in 'tunnel' container logs.")
        print("Make sure 'tunnel' service is running in docker-compose.yml.")
