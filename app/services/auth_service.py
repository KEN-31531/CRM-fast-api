"""認證服務"""
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models.db_models import Admin

# 密碼雜湊上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def hash_password(self, password: str) -> str:
        """雜湊密碼"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """驗證密碼"""
        return pwd_context.verify(plain_password, hashed_password)

    async def get_admin_by_username(self, db: AsyncSession, username: str) -> Admin | None:
        """根據帳號取得管理員"""
        result = await db.execute(
            select(Admin).where(Admin.username == username)
        )
        return result.scalar_one_or_none()

    async def authenticate(self, db: AsyncSession, username: str, password: str) -> Admin | None:
        """驗證管理員帳號密碼"""
        admin = await self.get_admin_by_username(db, username)
        if not admin:
            return None
        if not admin.is_active:
            return None
        if not self.verify_password(password, admin.hashed_password):
            return None

        # 更新最後登入時間
        admin.last_login = datetime.now()
        await db.commit()

        return admin

    async def create_admin(
        self,
        db: AsyncSession,
        username: str,
        password: str
    ) -> Admin:
        """建立管理員帳號"""
        hashed_password = self.hash_password(password)
        admin = Admin(
            username=username,
            hashed_password=hashed_password
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin

    async def init_default_admin(self, db: AsyncSession) -> dict:
        """初始化預設管理員帳號"""
        # 檢查是否已存在
        existing = await self.get_admin_by_username(db, "admin")
        if existing:
            return {"message": "管理員帳號已存在", "created": False}

        # 建立預設管理員
        await self.create_admin(db, "admin", "admin123")
        return {"message": "預設管理員建立成功 (admin / admin123)", "created": True}


auth_service = AuthService()
