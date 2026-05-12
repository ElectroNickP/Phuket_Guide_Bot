"""
POS API Client for the Telegram Bot.
Provides async HTTP interface to communicate with the standalone POS microservice.
All cash register, product, and tourist checkout operations go through this client.

Usage:
    from services.pos_client import pos_client

    products = await pos_client.get_products()
    session = await pos_client.open_session("Yamu", manager_id=123)
    sale = await pos_client.record_sale(session_id=1, pier="Yamu", ...)
"""
import aiohttp
from typing import Optional
from loguru import logger
from config import config


class POSClient:
    """Async HTTP client for the POS microservice."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base_url(self) -> str:
        return getattr(config, "POS_API_URL", "http://localhost:8000").rstrip("/")

    @property
    def api_key(self) -> str:
        key = getattr(config, "POS_API_KEY", None)
        if key and hasattr(key, "get_secret_value"):
            return key.get_secret_value()
        return str(key) if key else ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an HTTP request to the POS service."""
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(method, url, **kwargs) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    detail = data.get("detail", data.get("message", f"HTTP {resp.status}"))
                    logger.error(f"POS API error: {method} {path} → {resp.status}: {detail}")
                    raise POSClientError(resp.status, detail)
                return data
        except aiohttp.ClientError as e:
            logger.error(f"POS API connection error: {method} {path} → {e}")
            raise POSClientError(503, f"POS service unavailable: {e}")

    # ── Products ──────────────────────────────────────────────────────────

    async def get_products(self, category: str = None) -> list[dict]:
        """Get list of active products."""
        params = {}
        if category:
            params["category"] = category
        result = await self._request("GET", "/api/v1/products", params=params)
        return result.get("data", [])

    async def get_categories(self) -> list[str]:
        """Get list of product categories."""
        result = await self._request("GET", "/api/v1/products/categories")
        return result.get("data", [])

    async def sync_products(self) -> int:
        """Trigger product sync from Google Sheets."""
        result = await self._request("POST", "/api/v1/products/sync")
        return result.get("synced", 0)

    # ── Sessions ──────────────────────────────────────────────────────────

    async def get_active_session(self, pier: str) -> dict | None:
        """Get active session for a pier. Returns full data dict or None."""
        result = await self._request("GET", "/api/v1/sessions/active", params={"pier": pier})
        data = result.get("data", {})
        return data if data.get("active") else None

    async def get_session_with_report(self, pier: str) -> dict:
        """Get active session + daily report data."""
        result = await self._request("GET", "/api/v1/sessions/active", params={"pier": pier})
        return result.get("data", {})

    async def open_session(self, pier: str, manager_id: int, manager_name: str = None) -> dict:
        """Open a new cash session."""
        result = await self._request("POST", "/api/v1/sessions/open", json={
            "pier": pier,
            "manager_id": manager_id,
            "manager_name": manager_name,
        })
        return result.get("data", {})

    async def close_session(self, session_id: int, pier: str = None) -> dict:
        """Close an active session. Returns daily report."""
        result = await self._request("POST", "/api/v1/sessions/close", json={
            "session_id": session_id,
            "pier": pier,
        })
        return result

    async def get_session_report(self, session_id: int) -> dict:
        """Get detailed report for a specific session."""
        result = await self._request("GET", f"/api/v1/sessions/{session_id}/report")
        return result.get("data", {})

    # ── Sales ─────────────────────────────────────────────────────────────

    async def record_sale(
        self,
        session_id: int,
        pier: str,
        manager_id: int,
        items_data: list[dict],
        payment_type: str = "cash",
    ) -> dict:
        """
        Record a sale.
        items_data: [{'name': str, 'quantity': int, 'price': float}]
        """
        result = await self._request("POST", "/api/v1/sales", json={
            "session_id": session_id,
            "pier": pier,
            "manager_id": manager_id,
            "items": items_data,
            "payment_type": payment_type,
        })
        return result.get("data", {})

    async def get_daily_report(self, pier: str, date: str = None) -> dict:
        """Get daily sales report for a pier."""
        params = {"pier": pier}
        if date:
            params["report_date"] = date
        result = await self._request("GET", "/api/v1/sales/daily-report", params=params)
        return result.get("data", {})

    async def cancel_sale(self, sale_id: int) -> bool:
        """Cancel a sale."""
        try:
            await self._request("DELETE", f"/api/v1/sales/{sale_id}")
            return True
        except POSClientError:
            return False

    # ── Tourist Checkout ──────────────────────────────────────────────────

    async def checkout(
        self,
        items: list[dict],
        telegram_id: int = None,
        pier: str = "Online",
    ) -> dict:
        """
        Create a tourist checkout order with NSPK payment.
        items: [{'name': str, 'quantity': int, 'price': float}]
        Returns: {'order_id', 'pay_url', 'total_thb', 'total_rub', 'rate'}
        """
        result = await self._request("POST", "/api/v1/checkout", json={
            "items": items,
            "telegram_id": telegram_id,
            "pier": pier,
        })
        return result.get("data", {})

    async def get_order_status(self, order_id: int) -> dict:
        """Get status of a tourist order."""
        result = await self._request("GET", f"/api/v1/checkout/{order_id}/status")
        return result.get("data", {})

    # ── Health ────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Check if POS service is reachable."""
        try:
            result = await self._request("GET", "/health")
            return result.get("status") == "ok"
        except Exception:
            return False


class POSClientError(Exception):
    """Raised when POS API returns an error."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"POS API Error ({status_code}): {detail}")


# Singleton instance
pos_client = POSClient()
