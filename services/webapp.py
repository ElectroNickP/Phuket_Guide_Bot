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
from database.models import User, ReportSubmission
from sqlalchemy import select
from datetime import datetime

routes = web.RouteTableDef()

def get_static_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, 'web_app', 'static')

def validate_webapp_data(init_data: str, bot_token: str) -> dict | None:
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            return None
        
        hash_val = parsed_data.pop("hash")
        
        # Sort keys
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            user_data = json.loads(parsed_data.get("user", "{}"))
            return user_data
    except Exception as e:
        logger.error(f"Error validating WebApp init_data: {e}")
    return None

@routes.get('/')
async def index_handler(request):
    return web.FileResponse(os.path.join(get_static_path(), 'index.html'))

@routes.get('/api/schedule')
async def handle_get_schedule(request):
    init_data = request.query.get('initData')
    if not init_data:
        return web.json_response({"status": "error", "message": "Missing initData"}, status=401)
        
    user_data = validate_webapp_data(init_data, config.BOT_TOKEN.get_secret_value())
    if not user_data or not user_data.get('username'):
        return web.json_response({"status": "error", "message": "Invalid initData or missing username"}, status=401)
        
    username = user_data['username']
    
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
        init_data = req_data.get('initData')
        payload = req_data.get('payload', {})
        
        user_data = validate_webapp_data(init_data, config.BOT_TOKEN.get_secret_value())
        if not user_data or not user_data.get('username'):
            return web.json_response({"status": "error", "message": "Invalid auth"}, status=401)
            
        username = user_data['username']
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
