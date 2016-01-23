"""
Utilities to send mails.
"""

from temci.utils.settings import Settings
import subprocess
import typing as t
import logging


def hostname() -> str:
    return str(subprocess.check_output("hostname").strip())[2:-1]


def send_mail(recipient: str, subject: str, content: str, attached_files: t.List[str] = None):
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import smtplib
    if recipient == "":
        return
    sender = ""
    try:
        sender = "temci@" + hostname()
    except subprocess.CalledProcessError:
        sender = "temci@temci"
    try:
        attached_files = attached_files or []
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(content))
        for file in attached_files:
            try:
                with open(file, "r") as f:
                    msg_part = MIMEText(f.read())
                    msg_part.add_header('Content-Disposition', 'attachment', filename=file)
                    msg.attach(msg_part)
            except IOError:
                pass
        smtp = smtplib.SMTP("localhost")
        smtp.sendmail(sender, recipient, msg.as_string())
        smtp.quit()
    except BaseException as ex:
        logging.error(ex)