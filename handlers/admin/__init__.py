from aiogram import Router

# Initialize main admin router
admin_router = Router()

# Import all sub-routers
from .settings import router as settings_router
from .monitoring import router as monitoring_router
from .reports import router as reports_router
from .testing import router as testing_router
from .schedule import router as schedule_router
from .users import router as users_router

# Include them in the main router
admin_router.include_routers(
    settings_router,
    monitoring_router,
    reports_router,
    testing_router,
    schedule_router,
    users_router
)
