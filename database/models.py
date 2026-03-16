from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import datetime

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_contact = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Activity counters
    count_today = Column(Integer, default=0)
    count_tomorrow = Column(Integer, default=0)
    count_sea_today = Column(Integer, default=0)
    count_sea_tomorrow = Column(Integer, default=0)
    count_feedback = Column(Integer, default=0)
    count_status = Column(Integer, default=0)
    count_start = Column(Integer, default=0)

class Log(Base):
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    username = Column(String)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class ScheduleCache(Base):
    """Stores last known schedule to detect changes"""
    __tablename__ = 'schedule_cache'
    
    id = Column(Integer, primary_key=True)
    guide_username = Column(String)
    date = Column(DateTime)
    program_name = Column(String)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class AppSettings(Base):
    """Stores dynamic application settings like Spreadsheet ID"""
    __tablename__ = 'app_settings'
    
    key = Column(String, primary_key=True)
    value = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ReportSubmission(Base):
    """Tracks guide report submissions"""
    __tablename__ = 'report_submissions'
    
    id = Column(Integer, primary_key=True)
    guide_username = Column(String, nullable=False)
    program_name = Column(String, nullable=False)
    status = Column(String, default="ok") # "ok" or "problem"
    date = Column(DateTime, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
