from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import datetime
from utils.time import get_phuket_now

Base = declarative_base()

class UserRole:
    SUPER_ADMIN = 'super_admin'   # @pankonick
    ADMIN = 'admin'               # General admin
    HEAD_OF_GUIDE = 'head_guide'  # Can manage schedules/JO
    HOT_LINE = 'hotline'          # Coordination/Emergency
    PIER_MANAGER = 'pier_manager' # Pier coordination
    GUIDE = 'guide'               # Regular guide

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, unique=True)
    full_name = Column(String)
    role = Column(String, default=UserRole.GUIDE)
    guide_type = Column(String) # 'staff', 'freelance'
    created_at = Column(DateTime, default=get_phuket_now)
    last_contact = Column(DateTime, default=get_phuket_now)
    last_action = Column(String)
    
    # Activity counters
    count_today = Column(Integer, default=0)
    count_tomorrow = Column(Integer, default=0)
    count_sea_today = Column(Integer, default=0)
    count_sea_tomorrow = Column(Integer, default=0)
    count_feedback = Column(Integer, default=0)
    count_status = Column(Integer, default=0)
    count_start = Column(Integer, default=0)
    count_finish = Column(Integer, default=0)

class Log(Base):
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    username = Column(String)
    action = Column(String)
    timestamp = Column(DateTime, default=get_phuket_now)

class ScheduleCache(Base):
    """Stores last known schedule to detect changes"""
    __tablename__ = 'schedule_cache'
    
    id = Column(Integer, primary_key=True)
    guide_username = Column(String)
    date = Column(DateTime)
    program_name = Column(String)
    last_updated = Column(DateTime, default=get_phuket_now)

class AppSettings(Base):
    """Stores dynamic application settings like Spreadsheet ID"""
    __tablename__ = 'app_settings'
    
    key = Column(String, primary_key=True)
    value = Column(String)
    updated_at = Column(DateTime, default=get_phuket_now, onupdate=get_phuket_now)

class ReportSubmission(Base):
    """Tracks guide report submissions"""
    __tablename__ = 'report_submissions'
    
    id = Column(Integer, primary_key=True)
    guide_username = Column(String, nullable=False)
    program_name = Column(String, nullable=False)
    status = Column(String, default="ok") # "ok" or "problem"
    date = Column(DateTime, nullable=False)
    report_type = Column(String, default="start") # "start" or "finish"
    start_time = Column(String) # For "start" reports
    end_time = Column(String) # For "finish" reports
    timestamp = Column(DateTime, default=get_phuket_now)

class WakeUpConfirmation(Base):
    """Tracks guide wake-up confirmations"""
    __tablename__ = 'wakeup_confirmations'
    
    id = Column(Integer, primary_key=True)
    guide_username = Column(String, nullable=False)
    date = Column(DateTime, nullable=False) # Program date
    pickup_time = Column(String, nullable=False) # e.g. "08:50"
    program_name = Column(String) # e.g. "City Tour b1"
    status = Column(String, default="pending") # "pending", "confirmed", "problem", "no_response"
    sent_at = Column(DateTime, default=get_phuket_now)
    confirmed_at = Column(DateTime)

# ─── CASH REGISTER MODELS ───────────────────────────────────────────────

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    cost_price = Column(Integer, default=0)
    sale_price = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=get_phuket_now, onupdate=get_phuket_now)

class CashSession(Base):
    __tablename__ = 'cash_sessions'
    id = Column(Integer, primary_key=True)
    pier = Column(String, nullable=False)
    manager_id = Column(Integer, nullable=False) # Using telegram_id
    opened_at = Column(DateTime, default=get_phuket_now)
    closed_at = Column(DateTime)
    status = Column(String, default="open") # "open", "closed"

class Sale(Base):
    __tablename__ = 'sales'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('cash_sessions.id'))
    pier = Column(String, nullable=False)
    manager_id = Column(Integer, nullable=False)
    total_amount = Column(Integer, nullable=False)
    payment_type = Column(String, nullable=False) # "cash", "online"
    created_at = Column(DateTime, default=get_phuket_now)
    
    items = relationship("SaleItem", back_populates="sale")

class SaleItem(Base):
    __tablename__ = 'sale_items'
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey('sales.id'))
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_unit = Column(Integer, nullable=False)
    total_price = Column(Integer, nullable=False)
    
    sale = relationship("Sale", back_populates="items")
