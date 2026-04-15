import urllib.parse
import httpx
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseSSOClient(ABC):
    @abstractmethod
    def get_login_url(self) -> str:
        """取得 SSO 登入導向網址"""
        pass

    @abstractmethod
    def validate_ticket(self, ticket: str) -> dict:
        """驗證 SSO Ticket 並回傳使用者資訊"""
        pass

class MockSSOClient(BaseSSOClient):
    def __init__(self, mock_users: list):
        self.mock_users = mock_users

    def get_login_url(self) -> str:
        # 導向內建的模擬登入頁面
        return "/api/v1/sso/mock-login"

    def validate_ticket(self, ticket: str) -> dict:
        # Mock 模式下，ticket 即為模擬使用者的學號
        for user in self.mock_users:
            if user.get("student_id") == ticket:
                return {
                    "username": user.get("student_id"),
                    "email": user.get("email"),
                    "name": user.get("name"),
                    "role": user.get("role", "student")
                }
        raise ValueError("無效的模擬 Ticket或找不到此使用者")

class CASSSOClient(BaseSSOClient):
    def __init__(self, server_url: str, service_url: str, version: str = "3.0"):
        self.server_url = server_url.rstrip("/")
        self.service_url = service_url
        self.version = version

    def get_login_url(self) -> str:
        encoded_service = urllib.parse.quote(self.service_url, safe='')
        return f"{self.server_url}/login?service={encoded_service}"

    def validate_ticket(self, ticket: str) -> dict:
        encoded_service = urllib.parse.quote(self.service_url, safe='')
        # 注意: 依照真實 CAS 伺服器設定，可能是 /serviceValidate 或 /p3/serviceValidate
        validate_url = f"{self.server_url}/p3/serviceValidate?service={encoded_service}&ticket={ticket}"
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(validate_url)
                response.raise_for_status()
                
            # 使用簡單的字串解析抓取 XML 內容 (實務上考慮使用 xml.etree.ElementTree)
            if "cas:authenticationSuccess" in response.text:
                import re
                user_match = re.search(r'<cas:user>(.*?)<\/cas:user>', response.text)
                if user_match:
                    username = user_match.group(1).strip()
                    # 其他屬性如 email, role 可根據具體 CAS 伺服器回傳的 XML 做擴展解析
                    return {
                        "username": username,
                        "email": f"{username}@school.edu.tw", # Default fallback
                        "role": "student"                     # Default fallback
                    }
            logger.error(f"CAS ticket validation failed: {response.text}")
            raise ValueError("CAS 伺服器驗證 Ticket 失敗")
        except Exception as e:
            logger.error(f"CAS SSO Error: {e}")
            raise

def get_sso_client(mock_mode: bool = True, config: dict = None) -> BaseSSOClient:
    """工廠函式，根據設定回傳對應的 SSO 客戶端"""
    config = config or {}
    if mock_mode:
        mock_users = config.get("mock", {}).get("users", [])
        logger.info("使用 Mock SSO Client")
        return MockSSOClient(mock_users)
    else:
        cas_config = config.get("cas", {})
        server_url = cas_config.get("server_url", "")
        service_url = cas_config.get("service_url", "")
        version = cas_config.get("version", "3.0")
        logger.info(f"使用 Real CAS SSO Client (Server: {server_url})")
        return CASSSOClient(server_url, service_url, version)
