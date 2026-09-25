const processButton =
    document.getElementById(
        "processButton"
    );

const ticketForm =
    document.getElementById(
        "ticketForm"
    );


if (ticketForm) {

    ticketForm.addEventListener(
        "submit",
        submitTicket
    );
}

if (processButton) {

    processButton.addEventListener(
        "click",
        processSampleTicket
    );
}


async function submitTicket(event) {

    event.preventDefault();

    const button = document.getElementById(
        "submitTicketButton"
    );
    const status = document.getElementById(
        "formStatus"
    );
    const formData = new FormData(ticketForm);
    const ticket = Object.fromEntries(formData.entries());

    ticket.send_email = formData.has("send_email");
    button.disabled = true;
    button.textContent = "Processing ticket...";
    status.textContent = "Processing";

    try {
        const response = await fetch("/ticket", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ticket)
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Ticket submission failed.");
        }

        updateDashboard(data);
        status.textContent = "Submitted #" + data.ticket.ticket_id;
        ticketForm.reset();
    } catch (error) {
        status.textContent = "Error";
        alert(error.message);
    } finally {
        button.disabled = false;
        button.textContent = "Submit ticket for AI resolution";
    }
}


async function processSampleTicket() {

    processButton.disabled = true;

    processButton.textContent =
        "Processing Multi-Agent Workflow...";


    const ticket = {

        employee_name:
            "Arun",

        email:
            "arun@company.com",

        department:
            "Sales",

        title:
            "VPN Connection Failing on Corporate Network",

        description:
            "VPN timeout is occurring. I have an important client meeting and cannot work."
    };


    try {

        const response =
            await fetch(
                "/ticket",
                {

                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(ticket)
                }
            );


        const data =
            await response.json();


        if (!data.success) {

            alert(
                data.message
                || "Ticket processing failed."
            );

            return;
        }


        updateDashboard(
            data
        );

    }

    catch (error) {

        console.error(
            error
        );

        alert(
            "Unable to connect to SupportPilot."
        );

    }

    finally {

        processButton.disabled =
            false;

        processButton.textContent =
            "Process Sample VPN Ticket";
    }
}


function updateDashboard(data) {

    const classification =
        data.classification;


    document.getElementById(
        "category"
    ).textContent =
        classification.category;


    document.getElementById(
        "severity"
    ).textContent =
        classification.severity;


    document.getElementById(
        "priority"
    ).textContent =
        classification.priority;


    document.getElementById(
        "confidence"
    ).textContent =
        classification.confidence
        + "%";


    document.getElementById(
        "ticketStatus"
    ).textContent =
        data.ticket.status;

    const ticketOutcome = document.getElementById(
        "ticketOutcome"
    );

    ticketOutcome.className = "ticket-outcome " + data.ticket.status.replace(/\s+/g, "-");

    if (data.ticket.status === "Resolved") {
        ticketOutcome.textContent =
            "Completed and marked Resolved: the AI validated the ticket and no escalation was required.";
    } else if (data.ticket.status === "Escalated") {
        ticketOutcome.textContent =
            "Workflow completed, but the issue is not solved automatically: it was escalated for manual support.";
    } else {
        ticketOutcome.textContent =
            "Workflow completed, but the issue is not resolved yet: manual review is required.";
    }


    updateAgentStatus(
        data
    );


    updateActivity(
        data.workflow_activity
    );


    updateJira(
        data.integrations.jira
    );


    updateEmail(
        data.integrations.email,
        data.ticket
    );

    document.getElementById(
        "resolution"
    ).textContent =
        data.recommended_resolution;

    const resolutionState = document.getElementById(
        "resolutionState"
    );
    resolutionState.textContent = data.ticket.status;
    resolutionState.classList.add("complete");

}


function updateAgentStatus(data) {

    document.getElementById(
        "escalationStatus"
    ).textContent =
        data.escalation.escalate
        ? "Active"
        : "Standby";
}


function updateActivity(
    activities
) {

    const container =
        document.getElementById(
            "activityList"
        );


    container.innerHTML =
        "";


    activities.forEach(
        function(activity) {

            const row =
                document.createElement(
                    "div"
                );

            row.className =
                "activity-row";


            const time =
                document.createElement(
                    "span"
                );

            time.className =
                "activity-time";

            time.textContent =
                activity.time;


            const agent =
                document.createElement(
                    "span"
                );

            agent.className =
                "activity-agent";

            agent.textContent =
                activity.agent
                + ":";


            const message =
                document.createElement(
                    "span"
                );

            message.textContent =
                " "
                + activity.message;


            row.appendChild(
                time
            );

            row.appendChild(
                agent
            );

            row.appendChild(
                message
            );


            container.appendChild(
                row
            );
        }
    );
}


function updateJira(
    jira
) {

    document.getElementById(
        "jiraStatus"
    ).textContent =
        jira.status;


    document.getElementById(
        "jiraMessage"
    ).textContent =
        jira.configured
        ? "Connected • Live"
        : "Connected • Demo Mode";


    document.getElementById(
        "jiraTicketId"
    ).textContent =
        jira.ticket_id;


    document.getElementById(
        "jiraTicketStatus"
    ).textContent =
        jira.status;


    document.getElementById(
        "jiraPriority"
    ).textContent =
        jira.priority
        || "High";
}


function updateEmail(
    email,
    ticket
) {

    document.getElementById(
        "emailStatus"
    ).textContent =
        email.status;


    document.getElementById(
        "emailMessage"
    ).textContent =
        email.success
        ? "Sent • Live"
        : email.configured
            ? "Failed • Check SMTP"
            : "Not sent • Configure SMTP";


    document.getElementById(
        "emailNotificationText"
    ).textContent =

        email.success
        ? "Email sent to "
            + ticket.email
            + ". Ticket #"
            + ticket.ticket_id
            + " is available in your Gmail inbox."
        : email.message
        + " Ticket #"
        + ticket.ticket_id
        + " was processed, but no email was sent.";
}