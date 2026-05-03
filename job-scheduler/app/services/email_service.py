import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from ..config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, html_content: str):
    """
    ZH: 寄送電子郵件的核心方法
    EN: Core method to send emails
    """
    if not settings.SMTP_SERVER:
        logger.info(f"========== [MOCK EMAIL] ==========")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content: \n{html_content}")
        logger.info(f"==================================")
        return
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.ehlo()
        server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            
        server.sendmail(settings.SMTP_FROM_EMAIL, to_email, msg.as_string())
        server.quit()
        logger.info(f"Email successfully sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")

def send_login_alert(to_email: str, username: str, ip_address: str):
    """
    ZH: 寄送登入通知
    EN: Send login alert
    """
    subject = "AI Platform - New Login Alert"
    time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
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
    send_email(to_email, subject, html)

def send_password_change_alert(to_email: str, username: str):
    """
    ZH: 寄送密碼變更通知
    EN: Send password change alert
    """
    subject = "AI Platform - Password Changed Successfully"
    time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
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
    send_email(to_email, subject, html)

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
    send_email(to_email, subject, html)
