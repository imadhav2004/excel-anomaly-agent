import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_email(subject, body):
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    if dry_run:
        print("--- DRY RUN: email NOT sent ---")
        print(f"Subject: {subject}")
        print()
        print(body)
        return False

    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    receiver = os.getenv("EMAIL_RECEIVER")
    if not (sender and password and receiver):
        raise ValueError("Set EMAIL_SENDER, EMAIL_PASSWORD and EMAIL_RECEIVER in the .env file.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = receiver
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(message)
    print(f"Email sent to {receiver}")
    return True
