from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PublicOrderTrackingResponse(BaseModel):
    workshop_name: str
    site_name: Optional[str] = None
    order_number: str
    tracking_code: str
    status: str
    status_label: str
    status_message: str
    received_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    equipment_type: Optional[str] = None
    equipment_brand: Optional[str] = None
    equipment_model: Optional[str] = None
    serial_masked: str = Field(default="oculto")
    problem_summary: str
