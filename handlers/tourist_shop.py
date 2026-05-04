from aiogram import Router, types, F, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
from sqlalchemy import select
from database.db import AsyncSessionLocal
from database.models import Product, TouristOrder, TouristOrderItem
from services.payment_service import NSPKService
from utils.time import get_phuket_now

router = Router()

def get_categories_keyboard(categories):
    buttons = []
    # Two buttons per row
    for i in range(0, len(categories), 2):
        row = [InlineKeyboardButton(text=f"📂 {cat}", callback_data=f"tourist_cat_{cat}") for cat in categories[i:i+2]]
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_products_keyboard(products):
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(text=f"{p.name} — {p.sale_price}฿", callback_data=f"tourist_buy_{p.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="tourist_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "📦 Заказать в чате")
async def tourist_shop_main(message: types.Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product.category).where(Product.is_active == True).distinct())
        categories = [r[0] for r in result.all()]
    
    if not categories:
        await message.answer("📦 Магазин пока пуст. Заходите позже!")
        return

    await message.answer(
        "🛍 <b>Добро пожаловать в Best Sea Store!</b>\n\n"
        "Выберите категорию товаров:",
        reply_markup=get_categories_keyboard(categories),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "tourist_main")
async def tourist_shop_back(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product.category).where(Product.is_active == True).distinct())
        categories = [r[0] for r in result.all()]
    
    await callback.message.edit_text(
        "🛍 <b>Выберите категорию товаров:</b>",
        reply_markup=get_categories_keyboard(categories),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tourist_cat_"))
async def tourist_shop_cat(callback: types.CallbackQuery):
    cat = callback.data.replace("tourist_cat_", "")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Product).where(Product.category == cat, Product.is_active == True)
        )
        products = result.scalars().all()
    
    if not products:
        await callback.answer("В этой категории пока нет товаров.")
        return

    await callback.message.edit_text(
        f"🛍 <b>Категория: {cat}</b>\n\nВыберите товар:",
        reply_markup=get_products_keyboard(products),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tourist_buy_"))
async def tourist_shop_buy(callback: types.CallbackQuery):
    product_id = int(callback.data.replace("tourist_buy_", ""))
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        
        if not product:
            await callback.answer("Товар не найден.")
            return

        # Checkout flow
        await callback.message.edit_text(f"⏳ Генерирую ссылку на оплату для <b>{product.name}</b>...", parse_mode="HTML")
        
        nspk = NSPKService()
        pay_info = nspk.create_order(product.sale_price)
        
        if not pay_info:
            await callback.message.edit_text("❌ Извините, произошла ошибка при создании заказа. Попробуйте позже.")
            return

        # Save to DB
        order = TouristOrder(
            telegram_id=callback.from_user.id,
            pier="Chat_Native",
            total_amount=product.sale_price,
            status="pending",
            payment_reference=pay_info['reference'],
            payment_link=pay_info['link']
        )
        session.add(order)
        await session.flush()
        
        item = TouristOrderItem(
            order_id=order.id,
            product_name=product.name,
            quantity=1,
            price_per_unit=product.sale_price,
            total_price=product.sale_price
        )
        session.add(item)
        await session.commit()

        # Final message with Link
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить (NSPK)", url=pay_info['link'])],
            [InlineKeyboardButton(text="🛒 Назад в магазин", callback_data="tourist_main")]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Заказ #{order.id} сформирован!</b>\n\n"
            f"📦 Товар: {product.name}\n"
            f"💰 Сумма: {product.sale_price}฿ (~{pay_info['amount_rub']}₽)\n\n"
            f"Нажмите на кнопку ниже, чтобы оплатить через QR-код СБП:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await callback.answer()
