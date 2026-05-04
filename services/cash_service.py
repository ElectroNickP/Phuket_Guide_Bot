from database.db import AsyncSessionLocal
from database.models import Product, CashSession, Sale, SaleItem
from services.google_sheets import google_sheets
from utils.time import get_phuket_now
from sqlalchemy import select, update
from loguru import logger
import asyncio
import datetime

class CashService:
    async def sync_products(self) -> bool:
        """Syncs products from Google Sheets to database."""
        products_data = await google_sheets.get_store_price_list()
        if not products_data:
            logger.warning("No products found in Google Sheets to sync.")
            return False

        async with AsyncSessionLocal() as session:
            # Mark all as inactive first, then reactivate found ones
            await session.execute(update(Product).values(is_active=False))
            
            for p_info in products_data:
                query = select(Product).where(Product.name == p_info['name'])
                result = await session.execute(query)
                product = result.scalars().first()
                
                if product:
                    product.cost_price = p_info['cost_price']
                    product.sale_price = p_info['sale_price']
                    product.category = p_info['category']
                    product.is_active = True
                else:
                    new_product = Product(
                        name=p_info['name'],
                        cost_price=p_info['cost_price'],
                        sale_price=p_info['sale_price'],
                        category=p_info['category'],
                        is_active=True
                    )
                    session.add(new_product)

            
            await session.commit()
            logger.info(f"Synced {len(products_data)} products from Google Sheets.")
            return True

    async def get_active_products(self) -> list[Product]:
        """Returns list of active products."""
        async with AsyncSessionLocal() as session:
            # Order by name COLLATE NOCASE for case-insensitive alphabetical sorting
            from sqlalchemy import text
            query = select(Product).where(Product.is_active == True).order_by(text("name COLLATE NOCASE"))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_active_categories(self) -> list[str]:
        """Returns unique categories of active products."""
        async with AsyncSessionLocal() as session:
            from sqlalchemy import func
            query = select(Product.category).where(Product.is_active == True).distinct()
            result = await session.execute(query)
            return [r[0] for r in result.all()]


    async def get_active_session(self, pier: str) -> CashSession | None:
        """Returns active session for a pier if exists."""
        async with AsyncSessionLocal() as session:
            query = select(CashSession).where(
                CashSession.pier == pier,
                CashSession.status == "open"
            ).order_by(CashSession.id.desc())
            result = await session.execute(query)
            return result.scalars().first()
            
    async def get_last_session(self, pier: str) -> CashSession | None:
        """Returns the most recent session for a pier (open or closed)."""
        async with AsyncSessionLocal() as session:
            query = select(CashSession).where(
                CashSession.pier == pier
            ).order_by(CashSession.id.desc()).limit(1)
            result = await session.execute(query)
            return result.scalars().first()

    async def open_session(self, pier: str, manager_id: int) -> CashSession:
        """Opens a new cash session. Auto-syncs prices from Google Sheets first."""
        existing = await self.get_active_session(pier)
        if existing:
            return existing

        # Auto-sync products from Google Sheets on each new session open
        try:
            await self.sync_products()
            logger.info(f"Auto-synced products on session open for pier {pier}")
        except Exception as e:
            logger.warning(f"Auto-sync failed on session open: {e} (continuing anyway)")

        async with AsyncSessionLocal() as session:
            new_session = CashSession(
                pier=pier,
                manager_id=manager_id,
                status="open"
            )
            session.add(new_session)
            await session.commit()
            await session.refresh(new_session)
            return new_session

    async def close_session(self, session_id: int) -> bool:
        """Closes an active session."""
        async with AsyncSessionLocal() as session:
            query = select(CashSession).where(CashSession.id == session_id)
            result = await session.execute(query)
            cash_session = result.scalars().first()
            
            if cash_session:
                cash_session.status = "closed"
                cash_session.closed_at = get_phuket_now()
                await session.commit()
                return True
            return False

    async def get_daily_report(self, pier: str, date: datetime.date) -> dict:
        """
        Returns aggregated daily report for all sales on a pier for a given calendar date.
        Includes profit/margin analytics by cross-referencing product cost prices.
        """
        from sqlalchemy.orm import selectinload
        import datetime
        
        # Build timezone-aware start/end of day in Phuket time (UTC+7)
        tz_offset = datetime.timezone(datetime.timedelta(hours=7))
        day_start = datetime.datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=tz_offset)
        day_end = day_start + datetime.timedelta(days=1)
        
        async with AsyncSessionLocal() as session:
            # Fetch sales
            query = (
                select(Sale)
                .where(
                    Sale.pier == pier,
                    Sale.created_at >= day_start,
                    Sale.created_at < day_end
                )
                .options(selectinload(Sale.items))
                .order_by(Sale.created_at)
            )
            result = await session.execute(query)
            sales = result.scalars().all()
            
            # Fetch product cost prices for margin calculation
            products_result = await session.execute(select(Product))
            all_products = products_result.scalars().all()
            cost_map = {p.name: p.cost_price for p in all_products}
        
        report = {
            "date": date.strftime("%d.%m.%Y"),
            "total_amount": 0,
            "total_cost": 0,
            "total_profit": 0,
            "cash_amount": 0,
            "online_amount": 0,
            "sales_count": len(sales),
            "items_summary": {},
            "transactions": []
        }
        
        for sale in sales:
            report["total_amount"] += sale.total_amount
            if sale.payment_type == "cash":
                report["cash_amount"] += sale.total_amount
            else:
                report["online_amount"] += sale.total_amount
            
            tx_items = []
            for item in sale.items:
                name = item.product_name
                cost_per_unit = cost_map.get(name, 0)
                item_cost = cost_per_unit * item.quantity
                item_profit = item.total_price - item_cost
                
                report["total_cost"] += item_cost
                report["total_profit"] += item_profit
                
                if name not in report["items_summary"]:
                    report["items_summary"][name] = {
                        "qty": 0, "unit_price": item.price_per_unit,
                        "cost_price": cost_per_unit,
                        "subtotal": 0, "cost_total": 0, "profit": 0,
                        "cash": 0, "online": 0
                    }
                s = report["items_summary"][name]
                s["qty"] += item.quantity
                s["subtotal"] += item.total_price
                s["cost_total"] += item_cost
                s["profit"] += item_profit
                if sale.payment_type == "cash":
                    s["cash"] += item.total_price
                else:
                    s["online"] += item.total_price
                
                tx_items.append({
                    "name": item.product_name, "qty": item.quantity,
                    "price": item.price_per_unit, "total": item.total_price,
                    "cost": cost_per_unit
                })
            
            report["transactions"].append({
                "sale_id": sale.id,
                "time": sale.created_at.strftime("%H:%M") if sale.created_at else "?",
                "payment": sale.payment_type,
                "amount": sale.total_amount,
                "items": tx_items
            })
        
        # Calculate margin percentage
        report["margin_pct"] = round((report["total_profit"] / report["total_amount"] * 100), 1) if report["total_amount"] > 0 else 0
        
        return report

    async def record_sale(self, session_id: int, pier: str, manager_id: int, items_data: list[dict], payment_type: str) -> Sale:
        """
        Records a sale with multiple items.
        items_data format: [{'name': str, 'quantity': int, 'price': int}]
        """
        async with AsyncSessionLocal() as session:
            total_amount = sum(item['quantity'] * item['price'] for item in items_data)
            
            new_sale = Sale(
                session_id=session_id,
                pier=pier,
                manager_id=manager_id,
                total_amount=total_amount,
                payment_type=payment_type
            )
            session.add(new_sale)
            await session.flush() # Get sale ID
            
            for item in items_data:
                sale_item = SaleItem(
                    sale_id=new_sale.id,
                    product_name=item['name'],
                    quantity=item['quantity'],
                    price_per_unit=item['price'],
                    total_price=item['quantity'] * item['price']
                )
                session.add(sale_item)
            
            await session.commit()
            return new_sale

    async def get_session_report(self, session_id: int) -> dict:
        """Returns a detailed summary of sales for a session."""
        from sqlalchemy.orm import selectinload
        async with AsyncSessionLocal() as session:
            query = select(Sale).where(Sale.session_id == session_id).options(selectinload(Sale.items))
            result = await session.execute(query)
            sales = result.scalars().all()
            
            report = {
                "total_amount": 0,
                "cash_amount": 0,
                "online_amount": 0,
                "sales_count": len(sales),
                "items_summary": {},   # product_name -> {qty, unit_price, subtotal, cash, online}
                "transactions": []     # individual sale log
            }
            
            for sale in sales:
                report["total_amount"] += sale.total_amount
                if sale.payment_type == "cash":
                    report["cash_amount"] += sale.total_amount
                else:
                    report["online_amount"] += sale.total_amount
                
                tx_items = []
                for item in sale.items:
                    name = item.product_name
                    if name not in report["items_summary"]:
                        report["items_summary"][name] = {
                            "qty": 0,
                            "unit_price": item.price_per_unit,
                            "subtotal": 0,
                            "cash": 0,
                            "online": 0
                        }
                    s = report["items_summary"][name]
                    s["qty"] += item.quantity
                    s["subtotal"] += item.total_price
                    if sale.payment_type == "cash":
                        s["cash"] += item.total_price
                    else:
                        s["online"] += item.total_price
                    
                    tx_items.append({
                        "name": item.product_name,
                        "qty": item.quantity,
                        "price": item.price_per_unit,
                        "total": item.total_price
                    })
                
                report["transactions"].append({
                    "sale_id": sale.id,
                    "time": sale.created_at.strftime("%H:%M") if sale.created_at else "?",
                    "payment": sale.payment_type,
                    "amount": sale.total_amount,
                    "items": tx_items
                })
            
            return report

cash_service = CashService()
