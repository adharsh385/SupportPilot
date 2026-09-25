import os
import smtplib

from email.message import EmailMessage

from dotenv import load_dotenv


load_dotenv()


SMTP_SERVER = os.getenv(
    "SMTP_SERVER",
    ""
).strip()

SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "587"
    )
)

SMTP_EMAIL = os.getenv(
    "SMTP_EMAIL",
    ""
).strip()

SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD",
    ""
).replace(" ", "").strip()


def email_is_configured():

    return all([
        SMTP_SERVER,
        SMTP_EMAIL,
        SMTP_PASSWORD
    ])


def send_email_notification(
    employee_name,
    recipient,
    ticket_id,
    title,
    category,
    priority,
    resolution
):

    # ------------------------------------------
    # DEMO MODE
    # ------------------------------------------

    if not email_is_configured():

        return {

            "success":
                False,

            "configured":
                False,

            "mode":
                "Demo",

            "status":
                "Not sent",

            "recipient":
                recipient,

            "message":
                "Email was not sent. Configure SMTP to enable live delivery."
        }

    # ------------------------------------------
    # REAL EMAIL
    # ------------------------------------------

    message = EmailMessage()

    message["Subject"] = (
        "SupportPilot Ticket #"
        + str(ticket_id)
        + " - "
        + title
    )

    message["From"] = (
        SMTP_EMAIL
    )

    message["To"] = (
        recipient
    )

    body = (

        "Hello "
        + employee_name
        + ",\n\n"

        + "Your support ticket has been received.\n\n"

        + "Ticket ID: "
        + str(ticket_id)
        + "\n"

        + "Title: "
        + title
        + "\n"

        + "Category: "
        + category
        + "\n"

        + "Priority: "
        + priority
        + "\n\n"

        + "AI Resolution:\n"
        + resolution
        + "\n\n"

        + "Your ticket has been processed by "
        + "the SupportPilot multi-agent workflow.\n\n"

        + "Regards,\n"
        + "SupportPilot AI Support"
    )

    message.set_content(
        body
    )

    try:

        smtp_class = (
            smtplib.SMTP_SSL
            if SMTP_PORT == 465
            else smtplib.SMTP
        )

        with smtp_class(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=20
        ) as server:

            if SMTP_PORT != 465:
                server.starttls()

            server.login(
                SMTP_EMAIL,
                SMTP_PASSWORD
            )

            server.send_message(
                message
            )

        return {

            "success":
                True,

            "configured":
                True,

            "mode":
                "Live",

            "status":
                "Active",

            "recipient":
                recipient,

            "message":
                "Email notification sent successfully."
        }

    except Exception as error:

        error_message = str(error)

        if "535" in error_message:
            error_message = (
                "Gmail rejected the login. Create a new App Password "
                "for "
                + SMTP_EMAIL
                + " and update SMTP_PASSWORD."
            )

        return {

            "success":
                False,

            "configured":
                True,

            "mode":
                "Live",

            "status":
                "Action required",

            "recipient":
                recipient,

            "message":
                error_message
        }


def send_welcome_email(username, recipient):

    if not email_is_configured():
        return {
            "success": False,
            "configured": False,
            "message": "SMTP is not configured."
        }

    message = EmailMessage()
    message["Subject"] = "Welcome to SupportPilot"
    message["From"] = SMTP_EMAIL
    message["To"] = recipient
    message.set_content(
        "Hello "
        + username
        + ",\n\n"
        + "Your SupportPilot account has been created successfully.\n\n"
        + "You can now sign in and submit support tickets.\n\n"
        + "Regards,\nSupportPilot AI Support"
    )

    try:
        smtp_class = (
            smtplib.SMTP_SSL
            if SMTP_PORT == 465
            else smtplib.SMTP
        )

        with smtp_class(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=20
        ) as server:
            if SMTP_PORT != 465:
                server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(message)

        return {
            "success": True,
            "configured": True,
            "message": "Welcome email sent successfully."
        }

    except Exception as error:
        return {
            "success": False,
            "configured": True,
            "message": str(error)
        }
