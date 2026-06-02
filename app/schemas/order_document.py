from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrderDocumentFormat, OrderDocumentType


class OrderDocumentGenerate(BaseModel):
    document_type: OrderDocumentType
    format: OrderDocumentFormat = OrderDocumentFormat.A4


class OrderDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    service_order_id: UUID
    document_type: str
    document_format: str
    file_url: str
    generated_at: datetime
    generated_by_id: Optional[UUID] = None
    generated_by_name: Optional[str] = None
