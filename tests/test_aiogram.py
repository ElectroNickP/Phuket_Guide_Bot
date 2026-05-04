import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

class TestState(StatesGroup):
    test = State()

router = Router()

@router.message(F.text == "a")
async def handle_a(msg: Message, state: FSMContext):
    pass

print("Loaded")
