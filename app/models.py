from sqlalchemy import (
    Column, 
    Integer, 
    String, 
    Boolean, 
    DateTime, 
    BigInteger, 
    Float, 
    ForeignKey,
    Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime, timezone


# ==============================
# بازیکن
# ==============================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    referral_code = Column(String, unique=True, index=True)
    referred_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    # دعوت بازیکن
    referral_count = Column(Integer, default=0)
    referral_bonus_claimed = Column(Boolean, default=False)
    
    # =========================
    # جایزهٔ روزانه
    # =========================

    daily_reward_day = Column(Integer, default=1)

    last_daily_reward = Column(DateTime(timezone=True), nullable=True)
    
    # فیلدهای گیم
    coins = Column(BigInteger, default=0)
    energy = Column(Integer, default=1000)
    max_energy = Column(Integer, default=1000)
    profit_per_hour = Column(Integer, default=0)
    daily_clicks = Column(Integer, default=0)
    first_login = Column(Boolean, default=True)
    
    # فیلدهای زمان - با timezone=True
   
    last_energy_update = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_daily_reset = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_profit_collect = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    game_start_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # =========================
    # درآمد بازی
    # =========================

    # آیا پروفیت فعال شده؟
    # بعد از دعوت 2 نفر true می‌شود
    profit_unlocked = Column(Boolean, default=False)

    # لول پروفیت
    profit_level = Column(Integer, default=1)

    # مقدار درآمد هر 3 ساعت
    # مثال:
    # لول 1 => 500
    # لول 2 => 1500
    profit_per_3h = Column(Integer, default=0)

    # آخرین زمانی که کاربر پروفیت گرفت
    last_profit_claim = Column(DateTime(timezone=True), nullable=True)

    # مجموع کل پروفیت دریافت شده
    total_profit_claimed = Column(BigInteger, default=0)    

class RegistrationJob(Base):
    __tablename__ = "registration_jobs"

    id = Column(String(36), primary_key=True)
    username = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class Card(Base):
    __tablename__ = "cards"
 
    id = Column(Integer, primary_key=True, index=True)
 
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")   # دسته‌بندی
    image_url = Column(String(255), nullable=True)      # نام فایل عکس
 
    price = Column(Integer, default=500)               # قیمت پایه سطح ۱
    profit_increase = Column(Integer, default=25)      # پروفیت پایه (legacy)
 
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
 
 
# رابطه کاربر با کارت‌ها
class UserCard(Base):
    __tablename__ = "user_cards"
 
    id = Column(Integer, primary_key=True, index=True)
 
    user_id = Column(Integer, ForeignKey("users.id"))
    card_id = Column(Integer, ForeignKey("cards.id"))
 
    level = Column(Integer, default=1)                 # سطح فعلی کارت
    purchased_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
