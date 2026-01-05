from .customers import router as customers_router
from .analysis import router as analysis_router
from .admin import router as admin_router
from .email import router as email_router

__all__ = ["customers_router", "analysis_router", "admin_router", "email_router"]
