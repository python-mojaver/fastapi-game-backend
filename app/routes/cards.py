from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from database import get_db
from models import Card, UserCard, User
from routes.auth import get_current_user_from_token

router = APIRouter(
    prefix="/cards",
    tags=["Cards"]
)

# ============================================================
# تنظیمات
# قانون: هر 20 سکه قیمت = 1 پروفیت در ساعت
# مثال: قیمت 500 → profit_per_hour = 25
# کارت بعد از خرید 24 ساعت قفل است
# ============================================================
CARD_LOCK_HOURS = 24   # ساعت
MAX_CARD_LEVEL  = 10   # حداکثر سطح


def get_level_price(base_price: int, level: int) -> int:
    """
    قیمت هر سطح = base_price × 2^(level-1)
    سطح 1=500، سطح 2=1000، سطح 3=2000، ...
    """
    return int(base_price * (2 ** (level - 1)))


def get_level_profit(base_price: int, level: int) -> int:
    """
    پروفیت هر سطح = قیمت ÷ 20
    سطح 1=25، سطح 2=50، سطح 3=100، ...
    """
    return max(1, int(get_level_price(base_price, level) / 20))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_unlock_info(user_card: UserCard):
    """
    اطلاعات قفل بودن کارت
    کارت 24 ساعت بعد از آخرین خرید/ارتقا قفل است
    """
    if not user_card or not user_card.purchased_at:
        return None, 0, False

    purchased = user_card.purchased_at
    if purchased.tzinfo is None:
        purchased = purchased.replace(tzinfo=timezone.utc)

    unlock_at = purchased + timedelta(hours=CARD_LOCK_HOURS)
    now = utc_now()
    remaining = max(0, int((unlock_at - now).total_seconds()))
    is_locked = remaining > 0

    return unlock_at, remaining, is_locked


# ============================================================
# GET /cards/
# لیست همه کارت‌ها با وضعیت کاربر
# ============================================================
@router.get("/")
def get_cards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
    category: str = None  # فیلتر اختیاری
):
    query = db.query(Card).filter(Card.is_active == True)
    if category:
        query = query.filter(Card.category == category)
    cards = query.order_by(Card.category, Card.price).all()

    result = []
    for card in cards:
        user_card = db.query(UserCard).filter(
            UserCard.user_id == current_user.id,
            UserCard.card_id == card.id
        ).first()

        current_level = user_card.level if user_card else 0
        owned = current_level > 0

        unlock_at, remaining_seconds, is_locked = get_unlock_info(user_card) if owned else (None, 0, False)

        next_level = current_level + 1
        can_upgrade = owned and not is_locked and next_level <= MAX_CARD_LEVEL

        next_price  = get_level_price(card.price, next_level) if next_level <= MAX_CARD_LEVEL else None
        next_profit = get_level_profit(card.price, next_level) if next_level <= MAX_CARD_LEVEL else None

        current_profit = get_level_profit(card.price, current_level) if owned else 0

        # آدرس عکس برای کاتلین
        image_url = f"/static/cards/{card.image_url}" if card.image_url else None

        result.append({
            "id": card.id,
            "name": card.name,
            "description": card.description,
            "category": card.category or "general",
            "image": image_url,                           #  آدرس عکس برای کاتلین

            "current_level": current_level,
            "max_level": MAX_CARD_LEVEL,
            "price": get_level_price(card.price, next_level) if not owned else get_level_price(card.price, next_level),
            "base_price": card.price,
            "profit_per_hour": current_profit,            # پروفیت فعلی این کارت

            "owned": owned,
            "can_upgrade": can_upgrade,

            # اطلاعات قفل
            "is_locked": is_locked,
            "unlock_at": unlock_at.isoformat() if unlock_at else None,
            "remaining_seconds": remaining_seconds,

            # اطلاعات سطح بعدی
            "next_level": next_level if next_level <= MAX_CARD_LEVEL else None,
            "next_level_price": next_price,
            "next_level_profit": next_profit,
            "can_afford": (current_user.coins or 0) >= (next_price or 0),
        })

    # دسته‌بندی‌های موجود
    categories = list(set(c.category for c in db.query(Card).filter(Card.is_active == True).all() if c.category))

    return {
        "status": "success",
        "cards": result,
        "total_cards": len(result),
        "owned_cards": sum(1 for c in result if c["owned"]),
        "total_profit_per_hour": sum(c["profit_per_hour"] for c in result),
        "categories": sorted(categories),
        "user_coins": current_user.coins or 0,
    }


# ============================================================
# GET /cards/list
# مستقیم لیست آرایه برمیگردونه - برای کاتلین که List<CardItem> انتظار داره
# ============================================================
@router.get("/list")
def get_cards_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
    category: str = None
):
    # همان منطق get_cards ولی فقط آرایه برمیگردونه
    query = db.query(Card).filter(Card.is_active == True)
    if category:
        query = query.filter(Card.category == category)
    cards = query.order_by(Card.category, Card.price).all()

    result = []
    for card in cards:
        user_card = db.query(UserCard).filter(
            UserCard.user_id == current_user.id,
            UserCard.card_id == card.id
        ).first()

        current_level = user_card.level if user_card else 0
        owned         = current_level > 0
        unlock_at, remaining_seconds, is_locked = (
            get_unlock_info(user_card) if owned else (None, 0, False)
        )
        next_level  = current_level + 1
        can_upgrade = owned and not is_locked and next_level <= MAX_CARD_LEVEL
        next_price  = get_level_price(card.price, next_level)  if next_level <= MAX_CARD_LEVEL else None
        next_profit = get_level_profit(card.price, next_level) if next_level <= MAX_CARD_LEVEL else None
        current_profit = get_level_profit(card.price, current_level) if owned else 0
        image_url = f"/static/cards/{card.image_url}" if card.image_url else None

        result.append({
            "id":                card.id,
            "name":              card.name,
            "description":       card.description,
            "category":          card.category or "general",
            "image":             image_url,
            "current_level":     current_level,
            "max_level":         MAX_CARD_LEVEL,
            "base_price":        card.price,
            "price":             next_price,
            "profit_per_hour":   current_profit,
            "profit_per_3h":     current_profit * 3,
            "owned":             owned,
            "can_upgrade":       can_upgrade,
            "is_locked":         is_locked,
            "unlock_at":         unlock_at.isoformat() if unlock_at else None,
            "remaining_seconds": remaining_seconds,
            "next_level":        next_level if next_level <= MAX_CARD_LEVEL else None,
            "next_level_price":  next_price,
            "next_level_profit": next_profit,
            "can_afford":        (current_user.coins or 0) >= (next_price or 0),
        })

    #  مستقیم آرایه برمیگردونه
    return result


# ============================================================
# GET /cards/categories
# لیست دسته‌بندی‌ها
# ============================================================
@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    cards = db.query(Card.category).filter(Card.is_active == True).distinct().all()
    cats = sorted(set(c.category for c in cards if c.category))
    return {"status": "success", "categories": cats}


# ============================================================
# GET /cards/{card_id}
# جزئیات یک کارت با همه سطوح
# ============================================================
@router.get("/{card_id}")
def get_card_detail(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    card = db.query(Card).filter(Card.id == card_id, Card.is_active == True).first()
    if not card:
        raise HTTPException(status_code=404, detail="کارت پیدا نشد")

    user_card = db.query(UserCard).filter(
        UserCard.user_id == current_user.id,
        UserCard.card_id == card.id
    ).first()

    current_level = user_card.level if user_card else 0
    owned = current_level > 0
    unlock_at, remaining, is_locked = get_unlock_info(user_card) if owned else (None, 0, False)

    # همه سطوح
    levels = []
    for lvl in range(1, MAX_CARD_LEVEL + 1):
        levels.append({
            "level": lvl,
            "price": get_level_price(card.price, lvl),
            "profit_per_hour": get_level_profit(card.price, lvl),
            "is_current": lvl == current_level,
            "is_unlocked": lvl <= current_level,
        })

    image_url = f"/static/cards/{card.image_url}" if card.image_url else None

    return {
        "id": card.id,
        "name": card.name,
        "description": card.description,
        "category": card.category,
        "image": image_url,
        "owned": owned,
        "current_level": current_level,
        "max_level": MAX_CARD_LEVEL,
        "profit_per_hour": get_level_profit(card.price, current_level) if owned else 0,
        "is_locked": is_locked,
        "unlock_at": unlock_at.isoformat() if unlock_at else None,
        "remaining_seconds": remaining,
        "levels": levels,
        "user_coins": current_user.coins or 0,
    }


# ============================================================
# POST /cards/{card_id}/buy
# خرید (سطح ۱) یا ارتقا به سطح بعدی
# ============================================================
@router.post("/{card_id}/buy")
def buy_or_upgrade_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    card = db.query(Card).filter(Card.id == card_id, Card.is_active == True).first()
    if not card:
        raise HTTPException(status_code=404, detail="کارت پیدا نشد")

    user_in_db = db.query(User).filter(User.id == current_user.id).first()

    user_card = db.query(UserCard).filter(
        UserCard.user_id == current_user.id,
        UserCard.card_id == card.id
    ).first()

    current_level = user_card.level if user_card else 0
    owned = current_level > 0

    # بررسی قفل بودن
    if owned:
        _, remaining, is_locked = get_unlock_info(user_card)
        if is_locked:
            hours_left = round(remaining / 3600, 1)
            raise HTTPException(
                status_code=400,
                detail=f"این کارت قفل است. {hours_left} ساعت دیگر می‌توانید ارتقا دهید"
            )

    next_level = current_level + 1

    if next_level > MAX_CARD_LEVEL:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "max_level",
                "message": f"این کارت به بالاترین سطح ({MAX_CARD_LEVEL}) رسیده است",
            }
        )

    # قیمت و پروفیت
    price      = get_level_price(card.price, next_level)
    new_profit = get_level_profit(card.price, next_level)
    old_profit = get_level_profit(card.price, current_level) if owned else 0
    profit_add = new_profit - old_profit

    # بررسی موجودی
    if (user_in_db.coins or 0) < price:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "insufficient_coins",
                "message": "موجودی کافی نیست",
                "required": price,
                "available": user_in_db.coins or 0,
                "shortage": price - (user_in_db.coins or 0),
            }
        )

    now = utc_now()

    # کسر سکه
    user_in_db.coins -= price

    # افزایش پروفیت
    user_in_db.profit_per_3h   = (user_in_db.profit_per_3h   or 0) + profit_add * 3
    user_in_db.profit_per_hour = (user_in_db.profit_per_hour or 0) + profit_add

    # آپدیت UserCard
    unlock_at = now + timedelta(hours=CARD_LOCK_HOURS)
    if user_card:
        user_card.level = next_level
        user_card.purchased_at = now   # ریست کردن تایمر قفل
    else:
        user_card = UserCard(
            user_id=current_user.id,
            card_id=card.id,
            level=next_level,
            purchased_at=now,
        )
        db.add(user_card)

    db.commit()
    db.refresh(user_in_db)

    action = "خریداری" if not owned else "ارتقا"

    return {
        "status": "success",
        "message": f"کارت {card.name} به سطح {next_level} {action} شد",

        # اطلاعات کارت
        "id": card.id,
        "name": card.name,
        "category": card.category,
        "image": f"/static/cards/{card.image_url}" if card.image_url else None,

        # سطح
        "previous_level": current_level,
        "current_level": next_level,
        "max_level": MAX_CARD_LEVEL,

        # مالی
        "price_paid": price,
        "profit_added": profit_add,
        "profit_per_hour": new_profit,
        "total_profit_per_hour": user_in_db.profit_per_hour,
        "remaining_coins": user_in_db.coins,

        # قفل
        "owned": True,
        "can_upgrade": False,   # قفل شد
        "is_locked": True,
        "unlock_at": unlock_at.isoformat(),
        "remaining_seconds": CARD_LOCK_HOURS * 3600,

        # سطح بعدی
        "next_level": next_level + 1 if next_level < MAX_CARD_LEVEL else None,
        "next_level_price":  get_level_price(card.price,  next_level + 1) if next_level < MAX_CARD_LEVEL else None,
        "next_level_profit": get_level_profit(card.price, next_level + 1) if next_level < MAX_CARD_LEVEL else None,
        "is_max_level": next_level >= MAX_CARD_LEVEL,
    }


# ============================================================
# GET /cards/my/summary
# ============================================================
@router.get("/my/summary")
def get_my_cards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    user_cards = db.query(UserCard).filter(UserCard.user_id == current_user.id).all()

    result = []
    total_profit = 0

    for uc in user_cards:
        card = db.query(Card).filter(Card.id == uc.card_id, Card.is_active == True).first()
        if not card:
            continue
        profit = get_level_profit(card.price, uc.level)
        total_profit += profit
        unlock_at, remaining, is_locked = get_unlock_info(uc)
        image_url = f"/static/cards/{card.image_url}" if card.image_url else None
        result.append({
            "id": card.id,
            "name": card.name,
            "category": card.category,
            "image": image_url,
            "level": uc.level,
            "profit_per_hour": profit,
            "is_locked": is_locked,
            "unlock_at": unlock_at.isoformat() if unlock_at else None,
            "remaining_seconds": remaining,
            "purchased_at": uc.purchased_at.isoformat() if uc.purchased_at else None,
        })

    return {
        "status": "success",
        "owned_cards": result,
        "total_owned": len(result),
        "total_profit_per_hour": total_profit,
        "user_coins": current_user.coins or 0,
    }