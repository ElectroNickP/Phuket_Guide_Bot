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
from database.models import User, ReportSubmission, UserRole, Product, CashSession, Sale, SaleItem
from services.cash_service import cash_service
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
        return result.scalar_one_or_none()
        
async def get_authorized_user(request):
    """Unified user detection via initData OR Token fallback."""
    init_data = request.query.get('initData')
    token = request.query.get('token')
    
    if not init_data and request.method == 'POST':
        try:
            body = await request.json()
            init_data = body.get('initData')
            token = token or body.get('token')
        except: pass

    # 1. Standard Telegram Auth
    user_data = validate_webapp_data(init_data, config.BOT_TOKEN.get_secret_value())
    if user_data and user_data.get('id'):
        return int(user_data['id']), user_data.get('username')

    # 2. Token Fallback (for buggy clients like tdesktop)
    if token:
        user_id = verify_auth_token(token, config.BOT_TOKEN.get_secret_value())
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
        db_user = result.scalar_one_or_none()
        
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
            username = result.scalar_one_or_none()
            
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
                username = result.scalar_one_or_none()
        
        payload = req_data.get('payload', {})
        rep_type = payload.get('type')
        bot: Bot = request.app['bot']
        
        async with AsyncSessionLocal() as session:
            # Find User
            result = await session.execute(select(User).where(User.username == username))
            db_user = result.scalar_one_or_none()
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

    products = await cash_service.get_active_products()
    data = [{"id": p.id, "name": p.name, "cost_price": p.cost_price, "sale_price": p.sale_price} for p in products]
    return web.json_response({"status": "success", "data": data})

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
    from utils.time import get_phuket_now
    today = get_phuket_now().date()
    daily_report = await cash_service.get_daily_report(pier, today)
    
    session_data = await cash_service.get_active_session(pier)
    if session_data:
        return web.json_response({
            "status": "success", 
            "data": {
                "active": True,
                "id": session_data.id,
                "pier": session_data.pier,
                "opened_at": session_data.opened_at.isoformat() if session_data.opened_at else None,
                "report": daily_report
            }
        })
    else:
        return web.json_response({
            "status": "success", 
            "data": {
                "active": False,
                "report": daily_report if daily_report["sales_count"] > 0 else None
            }
        })

@routes.post('/api/pier/session/open')
async def handle_open_session(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    pier = req_data.get('pier')
    
    session_data = await cash_service.open_session(pier, user_id)
    return web.json_response({"status": "success", "session_id": session_data.id})

@routes.post('/api/pier/session/close')
async def handle_close_session(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    session_id = req_data.get('session_id')
    pier = req_data.get('pier')
    
    success = await cash_service.close_session(session_id)
    
    # Return the full daily report after closing
    from utils.time import get_phuket_now
    today = get_phuket_now().date()
    daily_report = await cash_service.get_daily_report(pier, today) if pier else None
    
    return web.json_response({
        "status": "success" if success else "error",
        "report": daily_report
    })

@routes.post('/api/pier/sale')
async def handle_pier_sale(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
        
    req_data = await request.json()
    payload = req_data.get('payload') # {session_id, items, payment_type, pier}
    
    try:
        sale = await cash_service.record_sale(
            session_id=payload['session_id'],
            pier=payload['pier'],
            manager_id=user_id,
            items_data=payload['items'], # [{'name', 'quantity', 'price'}]
            payment_type=payload['payment_type']
        )
        return web.json_response({"status": "success", "sale_id": sale.id})
    except Exception as e:
        logger.exception("Error recording sale from WebApp")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@routes.post('/api/pier/sync')
async def handle_pier_sync(request):
    user_id, username = await get_authorized_user(request)
    if not user_id:
        return web.json_response({"status": "error", "message": "Unauthorized"}, status=401)
    
    try:
        success = await cash_service.sync_products()
        return web.json_response({"status": "success" if success else "error"})
    except PermissionError:
        return web.json_response({"status": "error", "message": "Permission denied to spreadsheet"}, status=403)
    except Exception as e:
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
