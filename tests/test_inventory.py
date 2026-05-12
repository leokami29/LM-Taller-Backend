from decimal import Decimal

from app.core.enums import UserRole
from app.core.security import SecurityUtils
from app.db.models.inventory import InventoryItem
from app.db.models.user import User


def test_inventory_stock_cannot_go_negative(client, db_session, seed_company_and_admin):
    company, _admin = seed_company_and_admin
    tech = User(
        company_id=company.id,
        email="tech@test.com",
        full_name="Tech",
        hashed_password=SecurityUtils.hash_password("password123"),
        role=UserRole.TECHNICIAN,
    )
    db_session.add(tech)
    item = InventoryItem(
        company_id=company.id,
        sku="SKU-1",
        name="Repuesto",
        quantity_stock=Decimal("1"),
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    token = client.post(
        "/api/v1/auth/login",
        json={"email": "tech@test.com", "password": "password123"},
    ).json()["access_token"]

    res = client.post(
        f"/api/v1/inventory/{item.id}/stock",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "movement_type": "sale",
            "quantity_change": "-5",
        },
    )
    assert res.status_code == 400
