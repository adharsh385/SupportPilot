import pandas as pd
import streamlit as st

from database import get_all_tickets


st.set_page_config(
    page_title="SupportPilot Dashboard",
    page_icon="🛠️",
    layout="wide",
)


def load_ticket_data():
    rows = get_all_tickets()
    if not rows:
        return pd.DataFrame(
            columns=[
                "ticket_id",
                "employee_name",
                "email",
                "department",
                "title",
                "description",
                "category",
                "severity",
                "priority",
                "confidence",
                "status",
                "resolution",
                "created_at",
            ]
        )

    return pd.DataFrame(rows)


with st.sidebar:
    st.title("SupportPilot")
    st.caption("Operations Dashboard")
    st.markdown("---")
    st.write("Overview of ticket flow, priority mix, and support workload.")


st.title("Support Operations Dashboard")

tickets = load_ticket_data()

if tickets.empty:
    st.info("No tickets are in the system yet. Submit a ticket from the main app to populate the dashboard.")
    st.stop()

metrics = {
    "Total Tickets": int(len(tickets)),
    "Open": int((tickets["status"] == "Open").sum()),
    "Resolved": int((tickets["status"] == "Resolved").sum()),
    "Escalated": int((tickets["status"] == "Escalated").sum()),
}

col1, col2, col3, col4 = st.columns(4)
for column, value in zip((col1, col2, col3, col4), metrics.items()):
    label, metric_value = value
    column.metric(label, metric_value)

st.markdown("---")

category_counts = (
    tickets["category"].fillna("Unclassified").value_counts().rename_axis("category").reset_index(name="count")
)
priority_counts = (
    tickets["priority"].fillna("Unknown").value_counts().rename_axis("priority").reset_index(name="count")
)
status_counts = tickets["status"].fillna("Open").value_counts().rename_axis("status").reset_index(name="count")

left_col, right_col = st.columns(2)
with left_col:
    st.subheader("Tickets by Category")
    st.bar_chart(category_counts.set_index("category")["count"])

with right_col:
    st.subheader("Tickets by Priority")
    st.bar_chart(priority_counts.set_index("priority")["count"])

st.subheader("Current Ticket Status")
st.bar_chart(status_counts.set_index("status")["count"])

st.markdown("---")

st.subheader("Recent Tickets")
recent = tickets.sort_values("ticket_id", ascending=False).head(10).copy()
recent["confidence"] = recent["confidence"].fillna(0).astype(float)
recent["confidence"] = recent["confidence"].round(2)
recent = recent[
    [
        "ticket_id",
        "employee_name",
        "title",
        "category",
        "priority",
        "status",
        "confidence",
    ]
]
st.dataframe(recent, use_container_width=True, hide_index=True)

if "created_at" in tickets.columns:
    timeline = tickets[["ticket_id", "created_at", "status"]].copy()
    timeline["created_at"] = pd.to_datetime(timeline["created_at"], errors="coerce")
    timeline = timeline.dropna(subset=["created_at"])
    if not timeline.empty:
        st.subheader("Ticket Timeline")
        st.line_chart(
            timeline.groupby("created_at").size().rename("tickets_created")
        )
