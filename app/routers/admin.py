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
    db: AsyncSession = Depends(get_db)
):
    """上傳 CSV 檔案匯入顧客資料

    自動識別欄位順序，支援從檔名提取課程資訊
    """
    # 檢查檔案類型
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="請上傳 CSV 檔案")

    try:
        # 讀取檔案內容
        content = await file.read()
        content_str = content.decode('utf-8')

        # 從檔名提取課程資訊
        filename = file.filename.replace('.csv', '')
        course_info = extract_course_from_filename(filename)

        # 匯入資料
        result = await db_service.import_customers_smart(db, content_str, course_info)
        return result
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV 檔案編碼錯誤，請使用 UTF-8 編碼")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入失敗：{str(e)}")


def extract_course_from_filename(filename: str) -> dict | None:
    """從檔名提取課程資訊"""
    # 移除常見後綴
    for suffix in ["名單", "資料", "清單", "列表"]:
        filename = filename.replace(suffix, "")

    # 檢查課程類型
    if "完整課程" in filename:
        course_name = filename.replace("完整課程", "").strip()
        return {"name": course_name or filename, "type": "完整課程"}
    elif "體驗課程" in filename:
        course_name = filename.replace("體驗課程", "").strip()
        return {"name": course_name or filename, "type": "體驗課程"}

    return None
