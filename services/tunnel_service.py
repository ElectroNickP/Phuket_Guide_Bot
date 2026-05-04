import os
import asyncio
from loguru import logger
from config import config

class TunnelMonitorService:
    def __init__(self, shared_file: str = "/app/shared/tunnel_url.txt"):
        self.shared_file = shared_file
        self.last_url = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info(f"Tunnel monitor started. Watching {self.shared_file}")

    async def _monitor_loop(self):
        while self._running:
            try:
                if os.path.exists(self.shared_file):
                    with open(self.shared_file, "r") as f:
                        url = f.read().strip()
                        
                    if url and url != self.last_url:
                        logger.info(f"🆕 New Tunnel URL detected: {url}")
                        config.WEBAPP_URL = url
                        self.last_url = url
                        # Log it to the shared bot log as well
                        logger.success(f"Dynamic config updated: WEBAPP_URL={url}")
                
            except Exception as e:
                logger.error(f"Error in tunnel monitor: {e}")
            
            await asyncio.sleep(60) # Check every minute

    def stop(self):
        self._running = False

tunnel_monitor_service = TunnelMonitorService()
