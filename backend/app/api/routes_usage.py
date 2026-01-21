from fastapi import APIRouter, Depends

from app.core.deps import get_current_username
from app.infrastructure.usage_store import UsageStore

router = APIRouter(prefix="/me", tags=["usage"])


@router.get("/usage")
def my_usage(username: str = Depends(get_current_username)):
    store = UsageStore()
    return store.get_summary(username)
