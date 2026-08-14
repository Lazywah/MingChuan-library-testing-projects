import smtplib
import logging
from email.utils import make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from ..config import settings

logger = logging.getLogger(__name__)

def _record(to_email: str, subject: str, status: str, detail: str = None,
            kind: str = None, username: str = None, user_id: str = None,
            message_id: str = None) -> None:
    """
    ZH: 寫一筆寄信紀錄（自行開 session —— 本模組多由 BackgroundTasks 呼叫，沒有現成 db）。
        記錄失敗絕不影響寄信流程本身。
    EN: Persist one outbound-email record; never let logging break the send path.
    """
    try:
        from ..database import SessionLocal
        from .. import models
        db = SessionLocal()
        try:
            db.add(models.EmailLog(
                to_email=to_email, subject=subject, status=status,
                detail=(detail or None), kind=kind, username=username, user_id=user_id,
                message_id=(message_id or None),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"寫入寄信紀錄失敗（不影響寄信）: {e}")


def send_email(to_email: str, subject: str, html_content: str,
               kind: str = None, username: str = None, user_id: str = None):
    """
    ZH: 寄送電子郵件的核心方法。

        ⚠️ **「成功」的真正含意**：`sendmail()` 不拋錯只代表**中繼伺服器收下了**，
        **不代表已送達**。網域存在但信箱不存在（例如我們替教職員合成的
        `員編@me.mcu.edu.tw`）會被中繼接受，稍後才**非同步退信到寄件人信箱**——
        那封退信不會回到程式裡。故此處狀態記為 `sent`（已交付 SMTP），不宣稱送達。

        能明確捕捉的失敗：
          refused — 收件人在 SMTP 交談當下就被拒（`SMTPRecipientsRefused` 或
                    `sendmail()` 回傳的被拒清單）
          failed  — 連線 / TLS / 認證 / 其他例外
          mock    — 未設定 SMTP_SERVER，只印 log 不實際寄出
    EN: Core send. `sent` = accepted by relay, NOT delivered (async bounces are
        invisible to us). Captures refused recipients and hard failures.
    """
    # ZH: v3.5 自己產 Message-ID —— 退信(DSN)會夾帶原信的 Message-ID，這是把
    #     「非同步退信」對回「當初那一封」的唯一可靠鍵。交給 SMTP 伺服器自動產的話
    #     我們拿不到值，之後只能靠 to_email 猜，同一人寄過多封就會對錯。
    msg_id = make_msgid(domain=(settings.SMTP_FROM_EMAIL.split("@")[-1] or None))

    if not settings.SMTP_SERVER:
        logger.info(f"========== [MOCK EMAIL] ==========")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content: \n{html_content}")
        logger.info(f"==================================")
        _record(to_email, subject, "mock", "SMTP_SERVER 未設定，未實際寄出",
                kind, username, user_id, msg_id)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg["Message-ID"] = msg_id

        part = MIMEText(html_content, "html")
        msg.attach(part)

        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        try:
            server.ehlo()
            server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

            # ZH: sendmail 回傳 dict = 「部分收件人被拒」（其餘仍送出）；原本這個回傳值被丟掉
            refused = server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - 關閉失敗不影響已送出的信
                pass

        if refused:
            logger.warning(f"收件人被拒 {to_email}: {refused}")
            _record(to_email, subject, "refused", str(refused)[:400], kind, username, user_id, msg_id)
        else:
            # ZH: 措辭刻意不用「successfully sent」——那會讓人誤以為已送達
            logger.info(f"已交付 SMTP 伺服器（不代表已送達）: {to_email}")
            _record(to_email, subject, "sent", None, kind, username, user_id, msg_id)

    except smtplib.SMTPRecipientsRefused as e:
        logger.warning(f"收件人全部被拒 {to_email}: {e.recipients}")
        _record(to_email, subject, "refused", str(e.recipients)[:400], kind, username, user_id, msg_id)
    except Exception as e:
        logger.error(f"寄信失敗 {to_email}: {e}")
        _record(to_email, subject, "failed", str(e)[:400], kind, username, user_id, msg_id)

def send_login_alert(to_email: str, username: str, ip_address: str):
    """
    ZH: 寄送登入通知
    EN: Send login alert
    """
    subject = "AI Platform - New Login Alert"
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>We noticed a new login to your AI Platform account.</p>
            <ul>
                <li><strong>IP Address:</strong> {ip_address}</li>
                <li><strong>Time:</strong> {time_str}</li>
            </ul>
            <p>If this was you, you can ignore this message. If not, please contact your administrator immediately and change your password.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html, kind="login_alert", username=username)

def send_password_change_alert(to_email: str, username: str):
    """
    ZH: 寄送密碼變更通知
    EN: Send password change alert
    """
    subject = "AI Platform - Password Changed Successfully"
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>The password for your AI Platform account has been successfully changed.</p>
            <p><strong>Time:</strong> {time_str}</p>
            <p>If you did not make this change, please contact your administrator immediately to secure your account.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html, kind="password_change_alert", username=username)

def send_temp_password(to_email: str, username: str, temp_password: str, is_new_account: bool = False):
    """
    ZH: 寄送臨時密碼或新帳號通知
    EN: Send temporary password or new account alert
    """
    subject = "AI Platform - Account Provisioned" if is_new_account else "AI Platform - Password Reset"
    html = f"""
    <html>
        <body>
            <h2>Hello {username},</h2>
            <p>{'An account has been provisioned for you' if is_new_account else 'Your password has been reset'} on the AI Platform.</p>
            <p>Your temporary password is: <strong style="font-size: 18px; color: #10b981;">{temp_password}</strong></p>
            <p>Please log in and change your password immediately in the settings panel.</p>
            <br>
            <p>Best regards,<br>AI Platform Team</p>
        </body>
    </html>
    """
    send_email(to_email, subject, html,
               kind=("account_provisioned" if is_new_account else "password_reset"),
               username=username)
