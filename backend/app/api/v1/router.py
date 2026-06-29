from fastapi import APIRouter

from app.api.v1.organisations.router import router as organisations_router
from app.api.v1.users.router import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(users_router)
router.include_router(organisations_router)
