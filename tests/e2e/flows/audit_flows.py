from tests.e2e.config import TOURIST_BOT_USERNAME, STAFF_BOT_USERNAME

# A flow to verify the Tourist Bot's premium "Buddy Shop" experience
TOURIST_SHOP_FLOW = [
    # 1. Switch to Tourist Bot
    ("switch_bot", TOURIST_BOT_USERNAME),
    
    # 2. Start the bot
    ("send", "/start"),
    
    # 3. Expect the premium greeting and the Buddy Shop button + Native Order button
    ("expect", "Phuket Buddy"),
    ("expect", "🛍 Buddy shop"),
    ("expect", "📦 Заказать в чате"),
    
    # 4. Verify that staff-only buttons are MISSING (Lockdown check)
    ("expect_not", "Панель"), 
    ("expect_not", "План на море"),
    ("expect_not", "Мой статус"),
    
    # 5. Verify support button exists
    ("expect", "🆘 Поддержка"),
]

# A flow to verify the Staff Bot's operational dashboard
STAFF_DASHBOARD_FLOW = [
    ("switch_bot", STAFF_BOT_USERNAME),
    ("send", "/start"),
    
    # Staff bot should have "Моя Панель" and "Расписание"
    ("expect", "📱 Моя Панель"),
    ("expect", "📅 Моё расписание"),
    
    # It should NOT have the Tourist "Buddy Shop" button text (optional, but good for separation)
    # Actually, the staff bot HAS "🛍 Заказать онлайн" currently (or renamed to Buddy shop?)
    # Let's check keyboards.py: I renamed it to "🛍 Buddy shop" in main menu too.
    ("expect", "🛍 Buddy shop"),
]
