from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PDFDocumentCreate(BaseModel):
    service_order_id: Optional[UUID] = None
    document_type: str = Field(..., max_length=80)
    file_url: str = Field(..., max_length=1024)


class PDFDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    service_order_id: Optional[UUID]
    document_type: str
    file_url: str
    generated_by_id: Optional[UUID]
    generated_at: datetime
    updated_at: datetime
