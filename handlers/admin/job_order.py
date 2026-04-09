from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from utils.permissions import RoleFilter
from .base import ADMIN_ALL, IsAdminFilter

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

# Future extraction point for Job Order and General Schedule logic
# For now, this logic remains safely in legacy.py to prevent breaking changes 
# during the initial phase of the modularity transition.
