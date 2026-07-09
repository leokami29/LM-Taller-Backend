from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models.service_contract import ServiceContract
from app.db.session import get_db
from app.dependencies import PortalContext, get_portal_context
from app.schemas.service_contract import ServiceContractResponse
from app.services.contract_service import contract_is_active

router = APIRouter(prefix="/contracts", tags=["portal-contracts"])


@router.get("/", response_model=List[ServiceContractResponse])
def portal_list_contracts(
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> List[ServiceContract]:
    rows = (
        db.query(ServiceContract)
        .filter(
            ServiceContract.company_id == ctx.company_id,
            ServiceContract.customer_id == ctx.customer_id,
            ServiceContract.is_active.is_(True),
        )
        .order_by(ServiceContract.contract_number)
        .all()
    )
    return [r for r in rows if contract_is_active(r)]
