"""認證路由"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["認證"])


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminResponse(BaseModel):
    id: int
    username: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/login")
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """管理員登入"""
    admin = await auth_service.authenticate(
        db, login_data.username, login_data.password
    )

    if not admin:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    # 設定 session
    request.session["admin_id"] = admin.id
    request.session["admin_username"] = admin.username

    return {
        "success": True,
        "message": "登入成功",
        "admin": AdminResponse.model_validate(admin)
    }


@router.post("/logout")
async def logout(request: Request):
    """管理員登出"""
    request.session.clear()
    return {"success": True, "message": "登出成功"}


@router.get("/me")
async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """取得目前登入的管理員"""
    admin_id = request.session.get("admin_id")

    if not admin_id:
        raise HTTPException(status_code=401, detail="未登入")

    from sqlalchemy import select
    from app.models.db_models import Admin

    result = await db.execute(
        select(Admin).where(Admin.id == admin_id)
    )
    admin = result.scalar_one_or_none()

    if not admin or not admin.is_active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="無效的登入狀態")

    return {
        "admin": AdminResponse.model_validate(admin)
    }


@router.post("/init")
async def init_admin(db: AsyncSession = Depends(get_db)):
    """初始化預設管理員帳號"""
    result = await auth_service.init_default_admin(db)
    return result
