from fastapi import APIRouter

from src.api.users.v1.router import router as users_v1_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(users_v1_router)

router = APIRouter(prefix="/api")
router.include_router(v1_router)
