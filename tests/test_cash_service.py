import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.cash_service import cash_service
from services.google_sheets import google_sheets
from database.db import init_db
from unittest.mock import AsyncMock, patch

async def test_cash_flow():
    print("🚀 Starting Cash Register verification...")
    
    # Initialize DB (create tables)
    await init_db()
    
    # Mock Google Sheets product list
    mock_products = [
        {"name": "Reef shoes", "cost_price": 60, "sale_price": 400},
        {"name": "Repellent S", "cost_price": 0, "sale_price": 200},
        {"name": "Beer", "cost_price": 0, "sale_price": 120}
    ]
    
    with patch.object(google_sheets, 'get_store_price_list', AsyncMock(return_value=mock_products)):
        print("1. Testing product sync...")
        success = await cash_service.sync_products()
        assert success == True
        
        products = await cash_service.get_active_products()
        assert len(products) == 3
        print(f"✅ Synced {len(products)} products.")

    pier = "Yamu"
    manager_id = 123456789
    
    print(f"2. Testing session opening for {pier}...")
    session = await cash_service.open_session(pier, manager_id)
    assert session.status == "open"
    assert session.pier == pier
    print(f"✅ Session opened: ID={session.id}")
    
    print("3. Recording a sale...")
    cart = [
        {"name": "Reef shoes", "price": 400, "quantity": 2},
        {"name": "Beer", "price": 120, "quantity": 3}
    ]
    sale = await cash_service.record_sale(session.id, pier, manager_id, cart, "cash")
    assert sale.total_amount == (2 * 400) + (3 * 120)
    assert sale.payment_type == "cash"
    print(f"✅ Sale recorded: Total={sale.total_amount}฿")
    
    print("4. Testing session report...")
    report = await cash_service.get_session_report(session.id)
    assert report["total_amount"] == 1160
    assert report["items_summary"]["Reef shoes"] == 2
    assert report["items_summary"]["Beer"] == 3
    print(f"✅ Report verified: Total={report['total_amount']}฿, Items={report['items_summary']}")
    
    print("5. Closing session...")
    success = await cash_service.close_session(session.id)
    assert success == True
    
    active_session = await cash_service.get_active_session(pier)
    assert active_session is None
    print("✅ Session closed successfully.")
    
    print("\n✨ All Cash Register tests passed!")

if __name__ == "__main__":
    asyncio.run(test_cash_flow())
