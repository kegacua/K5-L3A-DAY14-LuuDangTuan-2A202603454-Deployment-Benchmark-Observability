"""
Cost guard (tiêu chí 8) — theo dõi và giới hạn chi phí LLM trong Redis.
"""
from datetime import date

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    return f"cost:daily:{date.today().isoformat()}"


def _monthly_key() -> str:
    return f"cost:monthly:{date.today().strftime('%Y-%m')}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        return
    try:
        daily_spend = float(r.get(_daily_key()) or 0.0)
        monthly_spend = float(r.get(_monthly_key()) or 0.0)
    except Exception:
        return

    if daily_spend >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget limit exceeded.",
        )
    if monthly_spend >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Monthly budget limit exceeded.",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K
    if r is not None:
        try:
            d_key = _daily_key()
            m_key = _monthly_key()
            pipe = r.pipeline()
            pipe.incrbyfloat(d_key, cost)
            pipe.expire(d_key, 86400 * 2)
            pipe.incrbyfloat(m_key, cost)
            pipe.expire(m_key, 86400 * 35)
            pipe.execute()
        except Exception:
            pass
    return cost
