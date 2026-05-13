from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models.company import Company
from app.db.models.platform_user import PlatformUser
from app.db.session import get_db
from app.dependencies import require_platform_super_admin
from app.schemas.platform import ImpersonateRequest, PlatformUserResponse
from app.schemas.tokens import PlatformTokenPairResponse
from app.services.audit_service import write_audit
from app.services.platform_auth_service import create_platform_token_pair

router = APIRouter(prefix="/impersonate", tags=["platform-impersonate"])


@router.post("", response_model=PlatformTokenPairResponse)
def impersonate_company(
    payload: ImpersonateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: PlatformUser = Depends(require_platform_super_admin),
) -> PlatformTokenPairResponse:
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    access, refresh = create_platform_token_pair(actor, act_as_company_id=payload.company_id)
    write_audit(
        db,
        actor_type="platform",
        actor_id=str(actor.id),
        action="platform.impersonate",
        company_id=payload.company_id,
        resource_type="company",
        resource_id=str(payload.company_id),
        metadata_json={"target_company": str(payload.company_id)},
        ip_address=request.client.host if request.client else None,
        detail=f"Impersonación empresa {company.name}",
    )
    db.commit()
    return PlatformTokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=PlatformUserResponse.model_validate(actor),
    )
