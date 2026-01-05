from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, init_db
from app.services import db_service

router = APIRouter(prefix="/admin", tags=["管理"])


@router.post("/init-db")
async def initialize_database():
    """初始化資料庫 (建立資料表)"""
    await init_db()
    return {"message": "資料庫初始化成功"}


@router.post("/import-csv")
async def import_csv_data(db: AsyncSession = Depends(get_db)):
    """從 CSV 檔案匯入資料（從固定路徑）"""
    return await db_service.import_csv_data(db)


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    course_name: str = Form(...),
    course_type: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """上傳 CSV 檔案匯入顧客資料

    CSV 格式：姓名,電話,Email,生日,參加活動時間,是否購買課程
    """
    # 檢查檔案類型
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="請上傳 CSV 檔案")

    # 檢查課程類型
    if course_type not in ["完整課程", "體驗課程"]:
        raise HTTPException(status_code=400, detail="課程類型必須是「完整課程」或「體驗課程」")

    try:
        # 讀取檔案內容
        content = await file.read()
        content_str = content.decode('utf-8')

        # 匯入資料
        result = await db_service.import_customers_from_csv(
            db, content_str, course_name, course_type
        )
        return result
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV 檔案編碼錯誤，請使用 UTF-8 編碼")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入失敗：{str(e)}")
