from fastapi import APIRouter, Depends

from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    """Retorna dados do usuário autenticado via JWT."""
    return current_user
