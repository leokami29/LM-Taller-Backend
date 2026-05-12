from fastapi import APIRouter

from app.api.v1.endpoints import admin, analytics, auth, customers, equipment, inventory, orders

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(customers.router)
router.include_router(equipment.router)
router.include_router(orders.router)
router.include_router(inventory.router)
router.include_router(analytics.router)
