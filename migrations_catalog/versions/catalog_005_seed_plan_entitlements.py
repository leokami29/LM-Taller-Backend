"""Seed plan_entitlements from PLAN_DEFAULTS."""

import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "catalog_005"
down_revision = "catalog_004"
branch_labels = None
depends_on = None

PLAN_IDS = {
    "starter": "a1000001-0000-4000-8000-000000000001",
    "pro": "a1000001-0000-4000-8000-000000000002",
    "enterprise": "a1000001-0000-4000-8000-000000000003",
}

STARTER_MODULES = ["core", "customers", "equipment", "orders", "admin_users"]
PRO_MODULES = STARTER_MODULES + ["inventory", "analytics"]
ENT_MODULES = PRO_MODULES + ["documents"]


EXTRA_FEATURES = [
    ("modules", "Módulos del plan", "module"),
    ("monthly_price_cop", "Precio mensual COP", "limit"),
    ("offline_grace_days", "Días grace offline", "limit"),
    ("max_days_without_sync", "Máx. días sin sync", "limit"),
    ("active_seats_limit", "Puestos desktop", "limit"),
    ("default_period_days", "Duración período (días)", "limit"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, name, kind in EXTRA_FEATURES:
        conn.execute(
            sa.text(
                "INSERT INTO feature_catalog (code, name, kind) VALUES (:c, :n, :k) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"c": code, "n": name, "k": kind},
        )
    seeds = [
        ("starter", STARTER_MODULES, 5, 100, 256, 29000, 7, 14, 1),
        ("pro", PRO_MODULES, 25, 1000, 2048, 99000, 14, 30, 3),
        ("enterprise", ENT_MODULES, 100, None, 10240, 299000, 30, 90, 10),
    ]
    for code, modules, max_u, max_o, storage, price, grace, sync_days, seats in seeds:
        pid = PLAN_IDS[code]
        conn.execute(sa.text("DELETE FROM plan_entitlements WHERE plan_id = :pid"), {"pid": pid})
        rows = [
            ("modules", {"modules": modules}),
            ("max_users", {"max_users": max_u}),
            ("monthly_price_cop", {"monthly_price_cop": price}),
            ("offline_grace_days", {"offline_grace_days": grace}),
            ("max_days_without_sync", {"max_days_without_sync": sync_days}),
            ("active_seats_limit", {"active_seats_limit": seats}),
            ("default_period_days", {"default_period_days": 30}),
        ]
        if max_o is not None:
            rows.append(("max_orders_month", {"max_orders_month": max_o}))
        if storage is not None:
            rows.append(("storage_mb", {"storage_mb": storage}))
        for feat, val in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO plan_entitlements (id, plan_id, feature_code, value_json) "
                    "VALUES (:id, :pid, :fc, CAST(:vj AS jsonb))"
                ),
                {"id": str(uuid4()), "pid": pid, "fc": feat, "vj": json.dumps(val)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    for pid in PLAN_IDS.values():
        conn.execute(sa.text("DELETE FROM plan_entitlements WHERE plan_id = :pid"), {"pid": pid})
