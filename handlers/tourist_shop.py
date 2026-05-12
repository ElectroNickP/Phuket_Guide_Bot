from aiogram import Router, types, F, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
from services.pos_client import pos_client, POSClientError
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
        buttons.append([InlineKeyboardButton(text=f"{p['name']} — {p['sale_price']}฿", callback_data=f"tourist_buy_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="tourist_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "📦 Заказать в чате")
async def tourist_shop_main(message: types.Message):
    try:
        categories = await pos_client.get_categories()
    except POSClientError:
        await message.answer("📦 Магазин временно недоступен. Попробуйте позже!")
        return
    
    if not categories:
        await message.answer("📦 Магазин пока пуст. Заходите позже!")
        return

    await message.answer(
        "🛒 <b>Добро пожаловать в Best Sea Store!</b>\n\n"
        "Выберите категорию товаров:",
        reply_markup=get_categories_keyboard(categories),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "tourist_main")
async def tourist_shop_back(callback: types.CallbackQuery):
    try:
        categories = await pos_client.get_categories()
    except POSClientError:
        await callback.answer("Магазин временно недоступен")
        return
    
    await callback.message.edit_text(
        "🛒 <b>Выберите категорию товаров:</b>",
        reply_markup=get_categories_keyboard(categories),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tourist_cat_"))
async def tourist_shop_cat(callback: types.CallbackQuery):
    cat = callback.data.replace("tourist_cat_", "")
    try:
        products = await pos_client.get_products(category=cat)
    except POSClientError:
        await callback.answer("Ошибка загрузки товаров")
        return
    
    if not products:
        await callback.answer("В этой категории пока нет товаров.")
        return

    await callback.message.edit_text(
        f"🛒 <b>Категория: {cat}</b>\n\nВыберите товар:",
        reply_markup=get_products_keyboard(products),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tourist_buy_"))
async def tourist_shop_buy(callback: types.CallbackQuery):
    product_id = int(callback.data.replace("tourist_buy_", ""))
    
    try:
        # Get all products and find the one we need
        products = await pos_client.get_products()
        product = next((p for p in products if p['id'] == product_id), None)
        
        if not product:
            await callback.answer("Товар не найден.")
            return

        # Checkout flow
        await callback.message.edit_text(f"⏳ Генерирую ссылку на оплату для <b>{product['name']}</b>...", parse_mode="HTML")
        
        # Create checkout through POS API
        checkout_result = await pos_client.checkout(
            items=[{
                'name': product['name'],
                'quantity': 1,
                'price': product['sale_price'],
            }],
            telegram_id=callback.from_user.id,
            pier="Chat_Native",
        )

        # Final message with Link
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить (NSPK)", url=checkout_result['pay_url'])],
            [InlineKeyboardButton(text="🛒 Назад в магазин", callback_data="tourist_main")]
        ])
        
        await callback.message.edit_text(
            f"✅ <b>Заказ #{checkout_result['order_id']} сформирован!</b>\n\n"
            f"📦 Товар: {product['name']}\n"
            f"💰 Сумма: {product['sale_price']}฿ (~{checkout_result.get('total_rub', '?')}₽)\n\n"
            f"Нажмите на кнопку ниже, чтобы оплатить через QR-код СБП:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await callback.answer()
    except POSClientError as e:
        await callback.message.edit_text(f"❌ Ошибка при создании заказа: {e.detail}")
    except Exception as e:
        logger.error(f"Tourist checkout error: {e}")
        await callback.message.edit_text("❌ Извините, произошла ошибка. Попробуйте позже.")
