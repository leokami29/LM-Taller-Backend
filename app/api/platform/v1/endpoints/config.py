import json
import os
from typing import Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import PLATFORM_COMPANIES_READ, PLATFORM_COMPANIES_WRITE
from app.dependencies import RequirePlatformPermission
from app.db.models.platform_user import PlatformUser

router = APIRouter(prefix="/config", tags=["platform-config"])

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "../../../../../platform_config.json")

class PlanConfig(BaseModel):
    monthly_price_cop: int
    max_active_users: int

class GlobalConfig(BaseModel):
    plans: Dict[str, PlanConfig]

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "plans": {
            "starter": {"monthly_price_cop": 99000, "max_active_users": 5},
            "pro": {"monthly_price_cop": 149000, "max_active_users": 15},
            "enterprise": {"monthly_price_cop": 299000, "max_active_users": 999}
        }
    }

def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

@router.get("/plans", response_model=GlobalConfig)
def get_plans_config(_user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_READ))):
    return load_config()

@router.put("/plans", response_model=GlobalConfig)
def update_plans_config(payload: GlobalConfig, _user: PlatformUser = Depends(RequirePlatformPermission(PLATFORM_COMPANIES_WRITE))):
    config = load_config()
    config["plans"] = payload.model_dump()["plans"]
    save_config(config)
    return config
