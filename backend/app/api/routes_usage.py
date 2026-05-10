from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.infrastructure.usage_store import UsageStore
from app.infrastructure.users_repository import UserRecord

router = APIRouter(prefix="/me", tags=["usage"])


@router.get("/usage")
def my_usage(current_user: UserRecord = Depends(get_current_user)):
    store = UsageStore()
    return store.get_summary(current_user.username)
