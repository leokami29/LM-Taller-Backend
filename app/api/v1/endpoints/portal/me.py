from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import PortalContext, get_portal_context
from app.db.models.service_contract import ServiceContract
from app.db.session import get_db
from app.schemas.portal import PortalMeResponse
from app.schemas.portal import PortalUserResponse
from app.schemas.service_contract import ServiceContractResponse
from app.services.contract_service import contract_is_active

router = APIRouter(tags=["portal-me"])


@router.get("/me", response_model=PortalMeResponse)
def portal_me(
    ctx: PortalContext = Depends(get_portal_context),
    db: Session = Depends(get_db),
) -> dict:
    contracts = (
        db.query(ServiceContract)
        .filter(
            ServiceContract.company_id == ctx.company_id,
            ServiceContract.customer_id == ctx.customer_id,
            ServiceContract.is_active.is_(True),
        )
        .all()
    )
    active = [c for c in contracts if contract_is_active(c)]
    return {
        "user": PortalUserResponse.model_validate(ctx.user),
        "customer_id": ctx.customer_id,
        "contracts": [ServiceContractResponse.model_validate(c) for c in active],
    }
