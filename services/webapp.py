import asyncio
from aiohttp import web
import aiohttp_cors
from loguru import logger
import os
import hmac
import hashlib
import urllib.parse
import json

from aiogram import Bot
from config import config
from services.google_sheets import google_sheets
from database.db import AsyncSessionLocal
from database.models import User, ReportSubmission, UserRole
from services.pos_client import pos_client, POSClientError
from utils.auth_tokens import verify_auth_token
from sqlalchemy import select, update
from datetime import datetime

routes = web.RouteTableDef()

def get_static_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'web_app', 'static')

def validate_webapp_data(init_data: str, bot_token: str) -> dict | None:
    try:
        if not init_data:
            logger.warning("WebApp: No initData provided")
            return None
            
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            logger.warning("WebApp: No hash in initData")
            return None
        
        hash_val = parsed_data.pop("hash")
        # Construction of data_check_string
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            user_data = json.loads(parsed_data.get("user", "{}"))
            logger.info(f"WebApp: Auth success for @{user_data.get('username')} (ID: {user_data.get('id')})")
            return user_data
        else:
            logger.error(f"WebApp: Hash mismatch! Calc: {calculated_hash}, Got: {hash_val}")
    except Exception as e:
        logger.error(f"WebApp: Error validating init_data: {e}")
    return None

async def get_user_role(telegram_id: int = None, username: str = None) -> str | None:
    async with AsyncSessionLocal() as session:
        logger.debug(f"Checking role for ID: {telegram_id}, Username: {username}")
        if telegram_id:
            result = await session.execute(select(User.role).where(User.telegram_id == telegram_id))
        elif username:
            result = await session.execute(select(User.role).where(User.username == username))
        else:
            return None
        return result.scalars().first()
        
async def get_authorized_user(request):
    """
    Checks authorization via Telegram initData OR a shared API Key.
    Returns (user_id, user_data) or (None, None).
    """
    # 1. Check for API Key (for browser/standalone access)
    api_key_header = request.headers.get('X-API-Key')
    api_key_query = request.query.get('api_key')
    provided_key = api_key_header or api_key_query
    
    if provided_key and provided_key == config.POS_API_KEY.get_secret_value():
        # Return a dummy admin user if API key matches
        return int(config.ADMIN_ID), {"id": config.ADMIN_ID, "username": "admin", "first_name": "Admin"}

    # 2. Check for Telegram initData
    init_data = request.query.get('initData')
    token = request.query.get('token')
    
    if not init_data and request.method == 'POST':
        try:
            body = await request.json()
            init_data = body.get('initData')
            token = token or body.get('token')
        except: pass

    # Collect all possible tokens
    tokens_to_try = [config.BOT_TOKEN.get_secret_value()]
    if config.BOT_TOKEN_STAFF:
        tokens_to_try.append(config.BOT_TOKEN_STAFF.get_secret_value())
    if config.BOT_TOKEN_TOURIST:
        tokens_to_try.append(config.BOT_TOKEN_TOURIST.get_secret_value())
    
    # 1. Standard Telegram Auth (Try all tokens)
    for bot_token in tokens_to_try:
        user_data = validate_webapp_data(init_data, bot_token)
        if user_data and user_data.get('id'):
            return int(user_data['id']), user_data.get('username')

    # 2. Token Fallback (Try all tokens)
    if token:
        for bot_token in tokens_to_try:
            user_id = verify_auth_token(token, bot_token)
            if user_id:
                return user_id, None
            
    return None, None

@routes.get('/api/init')
async def handle_init(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    async with AsyncSessionLocal() as session:
        # Fetch user details and role
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        db_user = result.scalars().first()
        
        if not db_user:
            return web.json_response({"status": "error", "message": "User not found"}, status=404)
            
        return web.json_response({
            "status": "success",
            "data": {
                "user_id": db_user.telegram_id,
                "username": db_user.username,
                "name": db_user.full_name,
                "role": db_user.role
            }
        })

@routes.get('/')
async def index_handler(request):
    return web.FileResponse(os.path.join(get_static_path(), 'index.html'))

@routes.get('/api/schedule')
async def handle_get_schedule(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    if not username: # If token auth was used, fetch username from DB
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User.username).where(User.telegram_id == user_id))
            username = result.scalars().first()
            
    if not username:
        return web.json_response({"status": "error", "message": "Username not determined"}, status=400)
    
    try:
        # Fetch 4-day schedule
        data = await google_sheets.get_guide_4day_data(username)
        # Transform into a format for WebApp
        frontend_data = []
        for item in data:
            if "FREE" in item['sched'] or "❌" in item['sched'] or not item['sched'].strip():
                continue
                
            # Basic parsing of string: 'P Phi Phi / SB-1 / 07:00 / 12'
            parts = [p.strip() for p in item['sched'].split('/')]
            program = parts[0] if len(parts) > 0 else 'Unknown'
            boat = parts[1] if len(parts) > 1 else ''
            pickup = parts[2] if len(parts) > 2 else ''
            pax = parts[3] if len(parts) > 3 else ''
            
            # If sea
            is_sea = len(parts) > 2
            
            frontend_data.append({
                "date": item['date'].strftime('%d.%m'),
                "type": "sea" if is_sea else "land",
                "program": program,
                "boat": boat,
                "pickup_time": pickup,
                "pax": pax if pax else "N/A"
            })
            
        return web.json_response({"status": "success", "data": frontend_data})
    except Exception as e:
        logger.exception("Error fetching schedule for WebApp")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@routes.post('/api/report')
async def handle_submit_report(request):
    try:
        req_data = await request.json()
        user_id, username = await get_authorized_user(request)
        if not user_id:
            return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
        if not username:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User.username).where(User.telegram_id == user_id))
                username = result.scalars().first()
        
        payload = req_data.get('payload', {})
        rep_type = payload.get('type')
        bot: Bot = request.app['bot']
        
        async with AsyncSessionLocal() as session:
            # Find User
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalars().first()
            if not db_user:
                return web.json_response({"status": "error", "message": "User not registered in bot"}, status=400)
                
            now = datetime.now()
            
            if rep_type == 'start':
                # Create start report in DB
                new_report = ReportSubmission(
                    guide_username=username,
                    report_type="start",
                    status="ok",
                    program_name=payload.get('program', 'Web App Program'),
                    date=datetime.now(),
                    start_time=payload.get('time')
                )
                session.add(new_report)
                await session.commit()
                
                # Notify Telegram
                msg = (f"🚀 <b>Web-App: Отчет о старте от @{username}</b>\n\n"
                       f"Программа: {new_report.program_name}\n"
                       f"Время: {payload.get('time')}\n"
                       f"Гости: {payload.get('adults')} взр. / {payload.get('children')} дет.\n"
                       f"Комментарий: {payload.get('comment')}")
                await bot.send_message(
                    chat_id=config.REPORT_GROUP_ID,
                    message_thread_id=config.REPORT_START_TOPIC_ID,
                    text=msg,
                    parse_mode="HTML"
                )
                
            elif rep_type == 'finish':
                # Create finish report in DB
                new_report = ReportSubmission(
                    guide_username=username,
                    report_type="finish",
                    status="ok",
                    program_name=payload.get('program', 'Web App Program'),
                    date=datetime.now(),
                    end_time=payload.get('time')
                )
                session.add(new_report)
                await session.commit()
                
                # Notify Telegram
                msg = (f"🏁 <b>Web-App: Отчет о финише от @{username}</b>\n\n"
                       f"Время финиша: {payload.get('time')}")
                await bot.send_message(
                    chat_id=config.REPORT_GROUP_ID,
                    message_thread_id=config.REPORT_FINISH_TOPIC_ID,
                    text=msg,
                    parse_mode="HTML"
                )
                
            else:
                return web.json_response({"status": "error", "message": "Invalid report type"}, status=400)
                
        return web.json_response({"status": "success"})
    except Exception as e:
        logger.exception("Error processing WebApp report")
        return web.json_response({"status": "error", "message": str(e)}, status=500)



# --- Pier Manager API ---

@routes.get('/api/pier/products')
async def handle_get_products(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)

    role = await get_user_role(telegram_id=user_id)
    if role not in [UserRole.PIER_MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.HEAD_OF_GUIDE]:
        logger.warning(f"API: Forbidden access for user {username} (ID: {user_id}) with role {role}")
        return web.json_response({"status": "error", "message": "Forbidden"}, status=403)

    try:
        products = await pos_client.get_products()
        logger.info(f"API: Returning {len(products)} active products for @{username}")
        data = [{"id": p['id'], "name": p['name'], "cost_price": p.get('cost_price', 0), "sale_price": p['sale_price'], "category": p.get('category', 'Other')} for p in products]
        return web.json_response({"status": "success", "data": data})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)



@routes.get('/api/pier/session')
async def handle_get_session(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    pier = request.query.get('pier')
    logger.info(f"API: GET /api/pier/session called for pier {pier}")
    
    # Check role
    role = await get_user_role(telegram_id=user_id)
    if role not in [UserRole.PIER_MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.HEAD_OF_GUIDE]:
        return web.json_response({"status": "error", "message": "Forbidden"}, status=403)
    
    # Always return the DAILY report (all sessions for today)
    try:
        session_data = await pos_client.get_session_with_report(pier)
        return web.json_response({"status": "success", "data": session_data})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/pier/session/open')
async def handle_open_session(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    pier = req_data.get('pier')
    
    try:
        result = await pos_client.open_session(pier, user_id)
        return web.json_response({"status": "success", "session_id": result.get('session_id')})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/pier/session/close')
async def handle_close_session(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    session_id = req_data.get('session_id')
    pier = req_data.get('pier')
    
    try:
        result = await pos_client.close_session(session_id, pier)
        return web.json_response(result)
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/pier/sale')
async def handle_pier_sale(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    payload = req_data.get('payload') # {session_id, items, payment_type, pier}
    
    try:
        sale = await pos_client.record_sale(
            session_id=payload['session_id'],
            pier=payload['pier'],
            manager_id=user_id,
            items_data=payload['items'],
            payment_type=payload['payment_type']
        )
        return web.json_response({"status": "success", "sale_id": sale.get('sale_id')})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)
    except Exception as e:
        logger.exception("Error recording sale from WebApp")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@routes.post('/api/pier/sync')
async def handle_pier_sync(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    try:
        count = await pos_client.sync_products()
        return web.json_response({"status": "success" if count > 0 else "error", "synced": count})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@routes.get('/api/pier/report')
async def handle_pier_report(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    pier = request.query.get('pier', '')
    if not pier:
        return web.json_response({"status": "error", "message": "Pier required"}, status=400)
    
    try:
        report = await pos_client.get_daily_report(pier)
        return web.json_response({"status": "success", "data": report})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)
    except Exception as e:
        logger.exception("Error fetching report")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# --- API v1 Proxy (for new POS UI compatibility) ---

@routes.get('/api/v1/sessions/active')
async def proxy_active_session(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    pier = request.query.get('pier')
    try:
        data = await pos_client.get_session_with_report(pier)
        return web.json_response({"status": "success", "data": data})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/v1/sessions/open')
async def proxy_open_session(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    body = await request.json()
    try:
        res = await pos_client.open_session(body.get('pier'), user_id)
        return web.json_response({"status": "success", "session_id": res.get('session_id')})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/v1/sessions/close')
async def proxy_close_session(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    body = await request.json()
    try:
        res = await pos_client.close_session(body.get('session_id'), body.get('pier'))
        return web.json_response(res)
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.get('/api/v1/products')
async def proxy_get_products(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    try:
        products = await pos_client.get_products()
        return web.json_response({"status": "success", "data": products})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/v1/products/sync')
async def proxy_sync_products(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    try:
        count = await pos_client.sync_products()
        return web.json_response({"status": "success", "synced": count})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/v1/sales')
async def proxy_record_sale(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    body = await request.json()
    try:
        res = await pos_client.record_sale(
            session_id=body['session_id'],
            pier=body['pier'],
            manager_id=user_id,
            items_data=body['items'],
            payment_type=body['payment_type']
        )
        return web.json_response({"status": "success", "sale_id": res.get('sale_id')})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.get('/api/v1/sales/daily-report')
async def proxy_daily_report(request):
    user_id, _ = await get_authorized_user(request)
    if not user_id: return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    pier = request.query.get('pier')
    try:
        report = await pos_client.get_daily_report(pier)
        return web.json_response({"status": "success", "data": report})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

# ─── TOURIST API ────────────────────────────────────────────────────────

@routes.get('/api/tourist/products')
async def tourist_products(request):
    """Public endpoint for browsing products — proxied to POS"""
    try:
        products = await pos_client.get_products()
        data = [{"id": p['id'], "name": p['name'], "price": p['sale_price'], "category": p.get('category', 'Other')} for p in products]
        return web.json_response({"status": "success", "products": data})
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.post('/api/tourist/checkout')
async def tourist_checkout(request):
    """Create order and generate NSPK payment link — proxied to POS"""
    try:
        data = await request.json()
        items = data.get('items', [])
        telegram_id = data.get('telegram_id')
        pier = data.get('pier', 'Yamu')
        
        if not items:
            return web.json_response({"status": "error", "message": "Cart is empty"}, status=400)

        # Normalize item format
        normalized_items = []
        for i in items:
            qty = i.get('quantity', i.get('qty', 1))
            normalized_items.append({
                'name': i['name'],
                'quantity': qty,
                'price': i['price'],
            })

        result = await pos_client.checkout(
            items=normalized_items,
            telegram_id=telegram_id,
            pier=pier,
        )
        
        return web.json_response({
            "status": "success",
            "order_id": result.get('order_id'),
            "pay_url": result.get('pay_url'),
            "total_rub": result.get('total_rub'),
            "total_thb": result.get('total_thb'),
        })
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@routes.get('/api/tourist/order/{id}')
async def tourist_order_status(request):
    order_id = request.match_info['id']
    try:
        result = await pos_client.get_order_status(int(order_id))
        return web.json_response({
            "status": "success",
            "order": {
                "id": result.get('order_id'),
                "status": result.get('order_status'),
                "amount": result.get('total_amount'),
            }
        })
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)

@routes.get('/tourist')
async def tourist_page(request):
    """Serve the tourist storefront"""
    static_path = get_static_path()
    file_path = os.path.join(static_path, 'tourist_shop.html')
    if os.path.exists(file_path):
        return web.FileResponse(file_path)
    return web.Response(text="Tourist store not found", status=404)

@routes.get('/api/products/active')
async def get_active_products(request):
    """Returns list of active products for the shop — proxied to POS"""
    try:
        products = await pos_client.get_products()
        return web.json_response({
            "status": "success",
            "data": [
                {
                    "id": p['id'],
                    "name": p['name'],
                    "sale_price": p['sale_price'],
                    "category": p.get('category', 'Other'),
                } for p in products
            ]
        })
    except POSClientError as e:
        return web.json_response({"status": "error", "message": e.detail}, status=e.status_code)
    except Exception as e:
        logger.error(f"Error fetching active products: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@routes.post('/api/webhook/payment')
async def handle_payment_webhook(request):
    """
    Receives payment confirmations from the POS service.
    """
    # 1. Verify API Key
    api_key = request.headers.get('X-API-Key')
    if api_key != config.POS_API_KEY.get_secret_value():
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    try:
        data = await request.json()
        logger.info(f"📩 Received payment webhook: {data}")
        
        status = data.get("status")
        order = data.get("order", {})
        
        if status == "paid":
            bot: Bot = request.app['bot']
            
            # Send notification to staff/group
            msg = (f"💰 <b>Оплата получена!</b>\n\n"
                   f"Заказ: #{order.get('id')}\n"
                   f"Сумма: {order.get('total_thb')} THB ({order.get('total_rub')} RUB)\n"
                   f"Пирс: {order.get('pier')}\n")
            
            if order.get('items'):
                msg += "\n🛒 <b>Состав заказа:</b>\n"
                for item in order['items']:
                    msg += f"• {item['name']} x{item['quantity']}\n"

            # Notify the manager group (using POS_LOG_TOPIC_ID for cash register logs)
            logger.info(f"📤 Sending payment notification to Chat:{config.REPORT_GROUP_ID}, Thread:{config.POS_LOG_TOPIC_ID}")
            await bot.send_message(
                chat_id=config.REPORT_GROUP_ID,
                message_thread_id=config.POS_LOG_TOPIC_ID,
                text=msg,
                parse_mode="HTML"
            )
            
            # Optionally notify the user directly
            user_id = order.get('telegram_id')
            if user_id:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text="✅ <b>Ваш заказ оплачен!</b>\n\nПожалуйста, покажите это сообщение менеджеру на пирсе для получения товара.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify user {user_id}: {e}")

        return web.json_response({"status": "success"})
        
    except Exception as e:
        logger.exception("Error processing payment webhook")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def setup_webapp(bot: Bot) -> web.AppRunner:
    """Configures and runs the aiohttp web app asynchronously"""
    app = web.Application()
    
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    
    app['bot'] = bot
    app.add_routes(routes)
    
    static_path = get_static_path()
    if os.path.exists(static_path):
        app.router.add_static('/static/', path=static_path, name='static')
    else:
        logger.warning(f"Static path {static_path} does not exist yet. Ensure you create it.")
        
    for route in list(app.router.routes()):
        cors.add(route)

    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', config.WEBAPP_PORT)
    await site.start()
    
    logger.info(f"🚀 Web App backend started at http://0.0.0.0:{config.WEBAPP_PORT}")
    return runner
