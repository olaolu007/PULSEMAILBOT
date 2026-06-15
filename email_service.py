from email.message import EmailMessage
import re
import smtplib, imaplib, email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os
from email.header import decode_header
from templates import apply_template



def clean_header(text: str) -> str:
    return re.sub(r'[\r\n]+', ' ', text).strip()

def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()  

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT")) 

def test_SMTP_connection(sender_email, app_password, smtp_server = None, smtp_port = None):
    try:
        smtp_server = smtp_server or SMTP_SERVER
        smtp_port = smtp_port or SMTP_PORT
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout= 10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, app_password)
        server.quit()
        return {
            "status": True,
            "message": "SMTP connection successful!"
        }
    except smtplib.SMTPAuthenticationError:
        return {
            "status" : False,
            "message": " Authentication Failed (Check Email & App Password)"
        }
    except smtplib.SMTPConnectError:
        return {
            "status" : False,
            "message": " Cannot connect to STMP server"
        }
    except Exception as e:
        return {
            "status": False,
            "message": f"SMTP ERROR: {str(e)}"
        }

def send_email(sender_email, app_password, receiver, subject, body, email_format="plain", template_name=None):
    try: 
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver
        msg["Reply To"] = sender_email
        msg["X-Mailer"] = "PulseMail Bot" 
        
        
        if email_format == "plain":
            msg.attach(MIMEText(body, "plain") )
            
        elif email_format == "html":
            msg.attach(MIMEText(body,"html"))
            
        elif email_format == "template":
            if not template_name:
                return {"Status": False, "message": "template_name is required for template format"}
            template_html = apply_template(template_name, subject, body)
            
            plain_version = (
                body.replace("<br>", "\n")
                    .replace("</p>", "\n")
                    .replace("</p>", "")
            )
            
            msg.attach(MIMEText(plain_version, "plain"))
            msg.attach(MIMEText(template_html, "html"))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        server.starttls()
        
        server.ehlo()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver, msg.as_string())
        server.quit()
        
        return {
            "status": True,
            "message": "Email sent successfully!"
        }
    except smtplib.SMTPAuthenticationError:
        return {
            "status" : False,
            "message": " Authentication Failed (Check Email & App Password)"
        }
    except smtplib.SMTPConnectError:
        return {
            "status" : False,
            "message": " Cannot connect to STMP server"
        }
    except Exception as e:
        return {
            "status": False,
            "message": f"SMTP ERROR: {str(e)}"
        }

def fetch_inbox(email_user, password):


    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(email_user, password)

        imap.select("INBOX")

        status, messages = imap.search(None, "ALL")

        mail_ids = messages[0].split()
        latest = mail_ids[-20:]

        inbox = []

        for mail_id in reversed(latest):
            res, msg = imap.fetch(mail_id, "(RFC822)")

            for response in msg:
                if isinstance(response, tuple):

                    msg = email.message_from_bytes(response[1])

                    subject, enc = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(enc or "utf-8")

                    sender = msg.get("From")

                    body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                            elif part.get_content_type() == "text/html" and not body:
                                body = strip_html(part.get_payload(decode=True).decode())
                    else:
                        body = msg.get_payload(decode=True).decode()

                    body = strip_html(body)

                    inbox.append({
                        "from": sender,
                        "subject": subject,
                        "body": body[:1000],
                        "message_id": msg.get("Message-ID", None),
                        "references": msg.get("References", ""),
                        "in_reply_to": msg.get("In-Reply-To", "")
                    })
    

        imap.close()
        imap.logout()

        return inbox

    except Exception as e:
        return [{"from": "system", "subject": "Error", "body": str(e)}]
    
def send_email_reply(sender_email, password, receiver, subject, body, reply_to=None):
    try:
        msg = EmailMessage()
        msg["From"] = sender_email
        msg["To"] = clean_header(receiver)
        msg["Subject"] = clean_header(subject)

        msg.set_content(body)
            
        if reply_to:
            message_id = reply_to.get("message_id", "")
            references = reply_to.get("references", "")

            msg["In-Reply-To"] = message_id
            msg["References"]  = f"{references} {message_id}".strip()

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()

        return {"status": True, "message": "Reply sent successfully!"}

    except smtplib.SMTPAuthenticationError:
        return {"status": False, "message": "Authentication Failed (Check Email & App Password)"}

    except smtplib.SMTPConnectError:
        return {"status": False, "message": "Cannot connect to SMTP server"}

    except Exception as e:
        return {"status": False, "message": f"SMTP Error: {str(e)}"}