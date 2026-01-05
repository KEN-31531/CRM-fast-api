import os
import json
import base64
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# 執行緒池用於 OAuth 流程
_executor = ThreadPoolExecutor(max_workers=1)

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.base_path = Path(__file__).parent.parent.parent
        self.credentials_path = self.base_path / "credentials.json"
        self.token_path = self.base_path / "token.json"
        self._service = None

    def _get_credentials_from_env(self) -> Credentials | None:
        """從環境變數取得憑證"""
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            return None

        logger.info("使用環境變數中的 Gmail 憑證")

        # 建立 Credentials 物件
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )

        return creds

    def _run_oauth_flow(self):
        """在背景執行緒中執行 OAuth 流程"""
        # 讀取憑證檔案
        with open(self.credentials_path, 'r') as f:
            client_config = json.load(f)

        # 建立 Flow（支援 web 和 installed 類型）
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri='http://localhost:8080/'
        )

        # 取得授權 URL
        auth_url, _ = flow.authorization_url(prompt='consent')

        print(f"\n請在瀏覽器中開啟以下網址進行授權：\n{auth_url}\n")

        # 啟動本地伺服器接收回調
        import http.server
        import urllib.parse

        auth_code = None

        class OAuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal auth_code
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                if 'code' in params:
                    auth_code = params['code'][0]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write('授權成功！您可以關閉此視窗。'.encode('utf-8'))
                else:
                    self.send_response(400)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # 靜音日誌

        import webbrowser
        webbrowser.open(auth_url)

        server = http.server.HTTPServer(('localhost', 8080), OAuthHandler)
        server.handle_request()

        if auth_code:
            flow.fetch_token(code=auth_code)
            return flow.credentials
        else:
            raise Exception("OAuth 授權失敗")

    async def _get_service(self):
        """取得 Gmail API 服務"""
        if self._service:
            return self._service

        creds = None

        # 優先從環境變數取得憑證
        creds = self._get_credentials_from_env()

        # 如果環境變數沒有，嘗試從檔案讀取
        if not creds and self.token_path.exists():
            logger.info("使用 token.json 檔案中的憑證")
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        # 如果沒有有效的憑證，進行授權
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Token 已過期，正在重新整理...")
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        "找不到 Gmail API 憑證。請設定環境變數或下載憑證檔案：\n"
                        "方法 1: 設定環境變數 GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN\n"
                        "方法 2: 下載 credentials.json 並放置於專案根目錄"
                    )
                # 在執行緒池中執行 OAuth 流程，避免阻塞
                loop = asyncio.get_event_loop()
                creds = await loop.run_in_executor(_executor, self._run_oauth_flow)

            # 只有使用檔案模式時才儲存 token
            if not os.getenv("GOOGLE_CLIENT_ID"):
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())

        self._service = build('gmail', 'v1', credentials=creds)
        return self._service

    def _create_message(self, to: str, subject: str, body_html: str, sender: str = "me") -> dict:
        """建立 Email 訊息"""
        message = MIMEMultipart('alternative')
        message['to'] = to
        message['subject'] = subject

        # HTML 內容
        html_part = MIMEText(body_html, 'html', 'utf-8')
        message.attach(html_part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw}

    async def send_email(self, to: str, subject: str, body_html: str) -> dict:
        """發送 Email"""
        try:
            service = await self._get_service()
            message = self._create_message(to, subject, body_html)
            result = service.users().messages().send(userId='me', body=message).execute()
            return {"success": True, "message_id": result['id']}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_festival_greeting(
        self,
        to: str,
        customer_name: str,
        festival: str,
        custom_message: str = ""
    ) -> dict:
        """發送節慶祝賀信"""
        template = self.get_festival_template(festival, customer_name, custom_message)
        subject = template["subject"]
        body = template["body"]
        return await self.send_email(to, subject, body)

    def get_festival_template(self, festival: str, customer_name: str, custom_message: str = "") -> dict:
        """取得節慶 Email 模板"""
        templates = {
            "christmas": {
                "subject": "聖誕快樂！感謝您的支持",
                "body": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #1a365d 0%, #2d4a6f 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="margin: 0;">🎄 聖誕快樂 🎄</h1>
                    </div>
                    <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                        <p style="font-size: 16px;">親愛的 <strong>{customer_name}</strong> 您好，</p>
                        <p style="font-size: 16px; line-height: 1.8;">
                            在這溫馨的聖誕佳節，我們誠摯地向您獻上最溫暖的祝福！
                            感謝您一直以來對我們的支持與信任。
                        </p>
                        {f'<p style="font-size: 16px; line-height: 1.8; background: #fff; padding: 15px; border-radius: 8px;">{custom_message}</p>' if custom_message else ''}
                        <p style="font-size: 16px; line-height: 1.8;">
                            願您和家人度過一個充滿歡樂與幸福的聖誕節！
                        </p>
                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                            祝福您，<br>
                            <strong>CRM 系統團隊</strong>
                        </p>
                    </div>
                </div>
                """
            },
            "new_year": {
                "subject": "新年快樂！祝您新的一年萬事如意",
                "body": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #c53030 0%, #e53e3e 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="margin: 0;">🧧 新年快樂 🧧</h1>
                    </div>
                    <div style="background: #fff5f5; padding: 30px; border-radius: 0 0 10px 10px;">
                        <p style="font-size: 16px;">親愛的 <strong>{customer_name}</strong> 您好，</p>
                        <p style="font-size: 16px; line-height: 1.8;">
                            新春佳節即將到來，我們在此向您拜個早年！
                            感謝您過去一年的支持與愛護。
                        </p>
                        {f'<p style="font-size: 16px; line-height: 1.8; background: #fff; padding: 15px; border-radius: 8px;">{custom_message}</p>' if custom_message else ''}
                        <p style="font-size: 16px; line-height: 1.8;">
                            祝您新的一年：<br>
                            🎊 身體健康、萬事如意<br>
                            🎊 心想事成、財源廣進
                        </p>
                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                            恭賀新禧，<br>
                            <strong>CRM 系統團隊</strong>
                        </p>
                    </div>
                </div>
                """
            },
            "double_11": {
                "subject": "雙11購物節 專屬優惠等您來！",
                "body": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #d69e2e 0%, #ecc94b 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="margin: 0;">🛒 雙11購物節 🛒</h1>
                    </div>
                    <div style="background: #fffff0; padding: 30px; border-radius: 0 0 10px 10px;">
                        <p style="font-size: 16px;">親愛的 <strong>{customer_name}</strong> 您好，</p>
                        <p style="font-size: 16px; line-height: 1.8;">
                            一年一度的雙11購物節來囉！
                            我們為您準備了專屬優惠，千萬別錯過！
                        </p>
                        {f'<p style="font-size: 16px; line-height: 1.8; background: #fff; padding: 15px; border-radius: 8px;">{custom_message}</p>' if custom_message else ''}
                        <p style="font-size: 16px; line-height: 1.8;">
                            趕快來看看有什麼好康吧！
                        </p>
                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                            祝您購物愉快，<br>
                            <strong>CRM 系統團隊</strong>
                        </p>
                    </div>
                </div>
                """
            },
            "birthday": {
                "subject": "生日快樂！專屬您的生日祝福",
                "body": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #805ad5 0%, #9f7aea 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="margin: 0;">🎂 生日快樂 🎂</h1>
                    </div>
                    <div style="background: #faf5ff; padding: 30px; border-radius: 0 0 10px 10px;">
                        <p style="font-size: 16px;">親愛的 <strong>{customer_name}</strong> 您好，</p>
                        <p style="font-size: 16px; line-height: 1.8;">
                            今天是您的生日，我們在此獻上最真摯的祝福！
                        </p>
                        {f'<p style="font-size: 16px; line-height: 1.8; background: #fff; padding: 15px; border-radius: 8px;">{custom_message}</p>' if custom_message else ''}
                        <p style="font-size: 16px; line-height: 1.8;">
                            願您：<br>
                            🎈 年年有今日，歲歲有今朝<br>
                            🎈 心想事成，幸福美滿
                        </p>
                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                            生日快樂，<br>
                            <strong>CRM 系統團隊</strong>
                        </p>
                    </div>
                </div>
                """
            }
        }

        return templates.get(festival, {
            "subject": f"來自 CRM 系統的祝福",
            "body": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #1a365d 0%, #2d4a6f 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                    <h1 style="margin: 0;">💌 溫馨祝福 💌</h1>
                </div>
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <p style="font-size: 16px;">親愛的 <strong>{customer_name}</strong> 您好，</p>
                    <p style="font-size: 16px; line-height: 1.8;">
                        {custom_message if custom_message else '感謝您一直以來的支持！'}
                    </p>
                    <p style="font-size: 14px; color: #666; margin-top: 30px;">
                        誠摯祝福，<br>
                        <strong>CRM 系統團隊</strong>
                    </p>
                </div>
            </div>
            """
        })

    def get_available_festivals(self) -> list[dict]:
        """取得可用的節慶列表"""
        return [
            {"id": "christmas", "name": "聖誕節", "emoji": "🎄"},
            {"id": "new_year", "name": "農曆新年", "emoji": "🧧"},
            {"id": "double_11", "name": "雙11購物節", "emoji": "🛒"},
            {"id": "birthday", "name": "生日", "emoji": "🎂"},
        ]


email_service = EmailService()
