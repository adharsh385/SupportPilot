import os
import requests

from dotenv import load_dotenv


load_dotenv()


JIRA_URL = os.getenv(
    "JIRA_URL",
    ""
)

JIRA_EMAIL = os.getenv(
    "JIRA_EMAIL",
    ""
)

JIRA_API_TOKEN = os.getenv(
    "JIRA_API_TOKEN",
    ""
)

JIRA_PROJECT_KEY = os.getenv(
    "JIRA_PROJECT_KEY",
    ""
)


def jira_is_configured():

    return all([
        JIRA_URL,
        JIRA_EMAIL,
        JIRA_API_TOKEN,
        JIRA_PROJECT_KEY
    ])


def create_jira_ticket(
    ticket_id,
    title,
    description,
    category,
    priority,
    resolution
):

    # ------------------------------------------
    # DEMO MODE
    # ------------------------------------------

    if not jira_is_configured():

        demo_ticket_id = (
            "SP-"
            + str(ticket_id)
        )

        return {

            "success":
                True,

            "configured":
                False,

            "mode":
                "Demo",

            "status":
                "In Progress",

            "ticket_id":
                demo_ticket_id,

            "assignee":
                "Network Team",

            "priority":
                priority,

            "message":
                "Demo Jira ticket created successfully."
        }

    # ------------------------------------------
    # REAL JIRA
    # ------------------------------------------

    url = (
        JIRA_URL.rstrip("/")
        + "/rest/api/3/issue"
    )

    description_text = (
        "SupportPilot Ticket\n\n"
        "Category: "
        + category
        + "\n"
        + "Priority: "
        + priority
        + "\n\n"
        + "Description:\n"
        + description
        + "\n\n"
        + "AI Resolution:\n"
        + resolution
    )

    payload = {

        "fields": {

            "project": {

                "key":
                    JIRA_PROJECT_KEY
            },

            "summary":
                title,

            "description": {

                "type":
                    "doc",

                "version":
                    1,

                "content": [

                    {

                        "type":
                            "paragraph",

                        "content": [

                            {

                                "type":
                                    "text",

                                "text":
                                    description_text
                            }
                        ]
                    }
                ]
            },

            "issuetype": {

                "name":
                    "Task"
            }
        }
    }

    try:

        response = requests.post(

            url,

            json=payload,

            auth=(

                JIRA_EMAIL,

                JIRA_API_TOKEN
            ),

            headers={

                "Accept":
                    "application/json",

                "Content-Type":
                    "application/json"
            },

            timeout=15
        )

        if response.status_code in (
            200,
            201
        ):

            result = response.json()

            return {

                "success":
                    True,

                "configured":
                    True,

                "mode":
                    "Live",

                "status":
                    "In Progress",

                "ticket_id":
                    result.get(
                        "key",
                        "JIRA-TICKET"
                    ),

                "assignee":
                    "Network Team",

                "priority":
                    priority,

                "message":
                    "Jira ticket created successfully."
            }

        return {

            "success":
                False,

            "configured":
                True,

            "mode":
                "Live",

            "status":
                "Failed",

            "ticket_id":
                "Not Created",

            "message":
                "Jira returned HTTP "
                + str(
                    response.status_code
                )
        }

    except Exception as error:

        return {

            "success":
                False,

            "configured":
                True,

            "mode":
                "Live",

            "status":
                "Failed",

            "ticket_id":
                "Not Created",

            "message":
                str(error)
        }