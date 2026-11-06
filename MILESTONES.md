# SupportPilot Milestones

## Milestone 1: Ticket Resolution Workflow

Completed:

- Ticket creation with employee, department, title, description, and recipient email.
- Ticket classification into category, severity, priority, and confidence.
- Knowledge-base retrieval through the RAG pipeline.
- AI-generated resolution and step-by-step troubleshooting guidance.
- Validation and escalation decisions.
- Resolved, Escalated, and Needs Review ticket outcomes.
- Ticket history, dashboard summaries, analytics, and deletion controls.

## Milestone 2: Operations and Integrations

Completed:

- Dashboard with ticket metrics, recent tickets, actions, and navigation.
- AI Agent workflow visualization with aligned agent connectors.
- Jira integration support for escalated tickets.
- Email notification workflow with Gmail SMTP support.
- Demo Mode when SMTP is not configured.
- Clear email delivery states: Sent, Not sent, and Action required.
- Gmail authentication diagnostics for invalid App Passwords.
- Responsive layouts for dashboard, AI Agent, ticket history, analytics, and integrations.

### Gmail delivery requirement

Live email delivery requires a Gmail App Password for the account in `SMTP_EMAIL`.
The normal Gmail password will be rejected by Gmail SMTP. Copy `.env.example` to `.env`,
set `SMTP_EMAIL` and `SMTP_PASSWORD`, then restart the application before submitting
a ticket with email notification enabled.

## Milestone 4: Support Analytics and Escalation Monitoring

Completed:

- Streamlit dashboard reads ticket records and operational metrics from the SupportPilot SQLite database.
- KPI cards show ticket volume, AI resolution rate, measured resolution time, customer satisfaction, evaluated classifier accuracy, and knowledge-base coverage.
- Plotly charts show category volume, AI-resolved versus escalated tickets, and ticket volume by priority.
- Human intervention monitoring flags critical tickets, confidence below 70%, failed resolutions, customer requests for human support, and tickets already escalated for review.
- Dashboard ticket data refreshes automatically every 30 seconds; a manual refresh is also available.

Run the dashboard from the repository root with:

```powershell
python -m streamlit run dashboard_app.py
```

The main `app.py` remains the Flask application. Classifier accuracy is shown only after a labeled evaluation is run, and resolution time is shown only when resolution timestamps are recorded.
