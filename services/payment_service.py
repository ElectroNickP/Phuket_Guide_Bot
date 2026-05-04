import requests
import json
import urllib.parse
from loguru import logger

class NSPKService:
    def __init__(self, slug="perm_52edadbda3b3c235bad91e9e76025d4c", point_id=261):
        self.slug = slug
        self.point_id = point_id
        self.base_url = "https://asia-nspk.cc"
        self.session = requests.Session()
        
        # Configure headers to look like a browser
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })

    def _refresh_session(self):
        """Hit the landing page to get fresh cookies and XSRF token"""
        try:
            landing_url = f"{self.base_url}/point/{self.slug}/pay"
            self.session.get(landing_url, timeout=10)
            xsrf_token = self.session.cookies.get('XSRF-TOKEN')
            if xsrf_token:
                self.session.headers.update({
                    "X-XSRF-TOKEN": urllib.parse.unquote(xsrf_token)
                })
            return True
        except Exception as e:
            logger.error(f"NSPK session refresh failed: {e}")
            return False

    def get_rate(self):
        """Fetch current THB/RUB rate and token"""
        try:
            rate_url = f"{self.base_url}/api/public/points/{self.slug}/rate"
            r = self.session.get(rate_url, timeout=10)
            if r.status_code != 200:
                logger.error(f"NSPK rate fetch failed: {r.status_code}")
                return None
            
            data = r.json()
            return data.get('rate') # Contains 'rate' and 'rate_token'
        except Exception as e:
            logger.error(f"NSPK rate error: {e}")
            return None

    def create_order(self, amount_thb):
        """Generate a payment reference for the given THB amount"""
        if not self._refresh_session():
            return None
        
        rate_info = self.get_rate()
        if not rate_info:
            return None
        
        rate_value = rate_info.get('rate')
        rate_token = rate_info.get('rate_token')
        
        # Calculate RUB amount
        amount_rub = round(amount_thb * float(rate_value))
        
        order_url = f"{self.base_url}/api/recurring/new-order"
        payload = {
            "point_id": self.point_id,
            "payment_currency": "RUB",
            "payment_amount": amount_rub,
            "settlement_currency": "THB",
            "settlement_amount": amount_thb,
            "rate_token": rate_token,
            "type": "online"
        }
        
        try:
            r = self.session.post(order_url, json=payload, timeout=10)
            if r.status_code != 200:
                logger.error(f"NSPK order creation failed: {r.status_code} - {r.text}")
                return None
            
            res = r.json()
            payment_ref = res.get('payment_reference')
            if payment_ref:
                return {
                    "reference": payment_ref,
                    "link": f"{self.base_url}/pay/{payment_ref}",
                    "amount_rub": amount_rub,
                    "amount_thb": amount_thb,
                    "rate": rate_value
                }
            return None
        except Exception as e:
            logger.error(f"NSPK order error: {e}")
            return None
