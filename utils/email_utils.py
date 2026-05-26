import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
import logging

def send_attendance_email(to_email, subject, content):
    """发送考勤预警邮件"""
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', 465))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    sender = os.getenv('SMTP_SENDER', smtp_user)

    if not all([smtp_server, smtp_user, smtp_pass]):
        logging.error("Email configuration is incomplete. Please check SMTP_SERVER, SMTP_USER, and SMTP_PASS in .env")
        return False, "邮件配置不完整"

    try:
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = Header(f"考勤管理系统 <{sender}>", 'utf-8')
        message['To'] = Header(to_email, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        # 使用 SSL 连接
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, [to_email], message.as_string())
        
        return True, "发送成功"
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {str(e)}")
        return False, str(e)
