from fastapi import APIRouter

from app.api.v1.endpoints.portal import auth, contracts, me, orders

router = APIRouter(prefix="/portal")

router.include_router(auth.router)
router.include_router(me.router)
router.include_router(contracts.router)
router.include_router(orders.router)
