import logging
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics import accuracy_score, precision_score, recall_score

from agent import EscalationAgent
from classifier import process_ticket
from config import DATABASE_PATH
from database import initialize_database, update_ticket

DB_PATH = DATABASE_PATH
LOG_PATH = Path(__file__).resolve().parent / "dashboard" / "supportpilot.log"
logger = logging.getLogger("supportpilot")
logger.setLevel(logging.INFO)
if not any(
    getattr(handler, "baseFilename", None) == str(LOG_PATH)
    for handler in logger.handlers
):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(file_handler)


st.set_page_config(
    page_title="Dashboard and Optimization",
    page_icon="📊",
    layout="wide",
)


@st.cache_resource
def ensure_database_initialized():
    initialize_database()


@st.cache_data(ttl=30, show_spinner=False)
def load_ticket_data() -> pd.DataFrame:
    """Load ticket data from the SupportPilot SQLite database."""
    if not DB_PATH.exists():
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
                "resolved_at",
                "ai_processing_time_seconds",
                "ai_resolved",
                "escalated",
                "escalation_reason",
                "validation_status",
                "human_requested",
                "response_generation_time_seconds",
                "ai_response_succeeded",
                "csat",
            ]
        )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        query = "SELECT * FROM tickets ORDER BY ticket_id DESC"
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    if df.empty:
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
                "resolved_at",
                "ai_processing_time_seconds",
                "ai_resolved",
                "escalated",
                "escalation_reason",
                "validation_status",
                "human_requested",
                "response_generation_time_seconds",
                "ai_response_succeeded",
                "csat",
            ]
        )

    expected_columns = [
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
        "ai_processing_time_seconds",
        "csat",
    ]

    for column in expected_columns:
        if column not in df.columns:
            df[column] = None

    df = df.copy()
    df["ticket_id"] = pd.to_numeric(df["ticket_id"], errors="coerce").fillna(0).astype(int)
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0)
    df["status"] = df["status"].fillna("Open").astype(str)
    df["category"] = df["category"].fillna("Unclassified").astype(str)
    df["priority"] = df["priority"].fillna("P4").astype(str)
    df["severity"] = df["severity"].fillna("Medium").astype(str)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], errors="coerce", utc=True)
    df["ai_processing_time_seconds"] = pd.to_numeric(
        df["ai_processing_time_seconds"], errors="coerce"
    )
    df["response_generation_time_seconds"] = pd.to_numeric(
        df["response_generation_time_seconds"], errors="coerce"
    )
    for column in ("ai_resolved", "escalated", "human_requested", "ai_response_succeeded"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["csat"] = pd.to_numeric(df["csat"], errors="coerce")

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def calculate_kpis(df: pd.DataFrame) -> dict:
    total_tickets = int(len(df))

    if total_tickets == 0:
        return {
            "total_tickets": 0,
            "auto_resolution_rate": 0.0,
            "avg_ai_processing_time": None,
            "avg_ai_response_time": None,
            "customer_satisfaction": None,
            "customer_satisfaction_pct": None,
            "kb_coverage": 0.0,
            "resolution_success_rate": 0.0,
            "avg_resolution_time_seconds": None,
            "escalated": 0,
        }

    status_series = df["status"].astype(str).str.upper()
    resolved_statuses = {"RESOLVED", "AUTO-RESOLVED", "CLOSED"}
    ai_resolved_values = pd.to_numeric(
        df.get("ai_resolved", pd.Series(index=df.index, dtype="float64")),
        errors="coerce",
    )
    if ai_resolved_values.notna().any():
        auto_resolved = int(ai_resolved_values.eq(1).sum())
    else:
        auto_resolved = int(status_series.isin(resolved_statuses).sum())
    escalated = int(
        status_series.isin(
            {"ESCALATED", "ESCALATED TO JIRA", "NEEDS REVIEW", "REVIEW", "JIRA"}
        ).sum()
    )
    processing_time_values = None
    if "ai_processing_time_seconds" in df.columns:
        processing_time_values = pd.to_numeric(df["ai_processing_time_seconds"], errors="coerce").dropna()
    if (processing_time_values is None or processing_time_values.empty) and "response_generation_time_seconds" in df.columns:
        processing_time_values = pd.to_numeric(df["response_generation_time_seconds"], errors="coerce").dropna()
    if (processing_time_values is None or processing_time_values.empty) and "processing_time_seconds" in df.columns:
        processing_time_values = pd.to_numeric(df["processing_time_seconds"], errors="coerce").dropna()

    avg_processing_time = (
        float(processing_time_values.mean())
        if processing_time_values is not None and not processing_time_values.empty
        else None
    )
    response_time_values = pd.to_numeric(
        df.get(
            "response_generation_time_seconds",
            pd.Series(index=df.index, dtype="float64"),
        ),
        errors="coerce",
    ).dropna()
    avg_ai_response_time = (
        float(response_time_values.mean()) if not response_time_values.empty else None
    )

    satisfaction = pd.to_numeric(
        df.get("csat", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    customer_satisfaction = (
        float(satisfaction.mean()) if not satisfaction.empty else None
    )

    resolved_at = pd.to_datetime(
        df.get("resolved_at", pd.Series(index=df.index, dtype="object")),
        errors="coerce",
        utc=True,
    )
    created_at = pd.to_datetime(
        df.get("created_at", pd.Series(index=df.index, dtype="object")),
        errors="coerce",
        utc=True,
    )
    resolution_durations = (resolved_at - created_at).dt.total_seconds()
    resolution_durations = resolution_durations[
        resolution_durations.notna() & resolution_durations.ge(0)
    ]
    avg_resolution_time = (
        float(resolution_durations.mean())
        if not resolution_durations.empty
        else None
    )

    if "kb_coverage" in df.columns:
        kb_coverage = pd.to_numeric(df["kb_coverage"], errors="coerce").dropna()
        kb_coverage_pct = float(kb_coverage.mean()) if not kb_coverage.empty else 0.0
        if kb_coverage_pct <= 1:
            kb_coverage_pct *= 100
    else:
        kb_hits = df["resolution"].fillna("").astype(str).str.contains(
            "KB|Source:|knowledge", case=False, na=False
        )
        kb_coverage_pct = float(kb_hits.mean() * 100)

    auto_resolution_rate = (
        (auto_resolved / total_tickets) * 100 if total_tickets else 0.0
    )
    if "ai_response_succeeded" in df.columns:
        response_success = pd.to_numeric(
            df["ai_response_succeeded"], errors="coerce"
        ).dropna()
    else:
        response_success = pd.Series(dtype="float64")
    resolution_success_rate = (
        float(response_success.eq(1).mean() * 100)
        if not response_success.empty
        else auto_resolution_rate
    )

    return {
        "total_tickets": total_tickets,
        "auto_resolution_rate": round(auto_resolution_rate, 2),
        "avg_ai_processing_time": round(avg_processing_time, 2) if avg_processing_time is not None else None,
        "avg_ai_response_time": (
            round(avg_ai_response_time, 4)
            if avg_ai_response_time is not None
            else None
        ),
        "customer_satisfaction": round(customer_satisfaction, 2) if customer_satisfaction is not None else None,
        "customer_satisfaction_pct": (
            round(customer_satisfaction / 5 * 100, 2)
            if customer_satisfaction is not None
            else None
        ),
        "kb_coverage": round(kb_coverage_pct, 2),
        "resolution_success_rate": round(resolution_success_rate, 2),
        "avg_resolution_time_seconds": (
            round(avg_resolution_time, 2)
            if avg_resolution_time is not None
            else None
        ),
        "escalated": int(escalated),
    }


@st.cache_data(show_spinner=False)
def build_dashboard_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    for column in (
        "ticket_id",
        "employee_name",
        "description",
        "resolution",
        "resolved_at",
        "ai_resolved",
        "escalated",
        "escalation_reason",
        "validation_status",
        "human_requested",
        "ai_response_succeeded",
    ):
        if column not in frame.columns:
            frame[column] = None
    frame["status"] = frame["status"].fillna("Open").astype(str)
    frame["title"] = frame["title"].fillna("Untitled ticket").astype(str)
    frame["category"] = frame["category"].fillna("Unclassified").astype(str)
    frame["priority"] = frame["priority"].fillna("P4").astype(str).str.upper()
    frame["severity"] = frame["severity"].fillna("Medium").astype(str).str.title()
    frame["confidence"] = pd.to_numeric(frame["confidence"], errors="coerce").fillna(0)
    frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce")
    frame["status_upper"] = frame["status"].str.upper()
    frame["intervention_reasons"] = frame.apply(
        lambda row: "; ".join(escalation_reasons(row)), axis=1
    )
    frame["requires_human_review"] = frame["intervention_reasons"].ne("")
    frame["reason_flags"] = frame.apply(derive_reason_flags, axis=1)
    return frame


def _is_true(value) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def escalation_reasons(row) -> list[str]:
    reasons = []
    existing_reason_value = row.get("escalation_reason")
    existing_reason = (
        ""
        if existing_reason_value is None or pd.isna(existing_reason_value)
        else str(existing_reason_value).strip()
    )
    existing_reason_lower = existing_reason.casefold()

    priority = str(row.get("priority") or "").strip().upper()
    severity = str(row.get("severity") or "").strip().upper()
    if priority in {"CRITICAL", "P1"} or severity == "CRITICAL":
        reasons.append("Critical priority or severity")

    confidence = pd.to_numeric(row.get("confidence"), errors="coerce")
    if pd.notna(confidence):
        normalized_confidence = (
            float(confidence) if confidence <= 1 else float(confidence) / 100
        )
        if normalized_confidence < 0.70:
            reasons.append("AI confidence below 70%")

    status = str(row.get("status") or "").strip().casefold()
    if status in {"escalated", "escalated to jira", "needs review", "review", "jira"}:
        reasons.append("Ticket already escalated for review")

    if (
        _is_true(row.get("resolution_failed"))
        or (
            row.get("ai_response_succeeded") is not None
            and pd.notna(row.get("ai_response_succeeded"))
            and not _is_true(row.get("ai_response_succeeded"))
        )
        or str(row.get("validation_status") or "").strip().casefold()
        in {"failed", "invalid", "needs review"}
    ):
        if not any(term in existing_reason_lower for term in ("fail", "invalid")):
            reasons.append("AI resolution failed")

    if _is_true(row.get("human_requested")):
        if not (
            "human" in existing_reason_lower
            and ("request" in existing_reason_lower or "support" in existing_reason_lower)
        ):
            reasons.append("Customer requested human support")

    if existing_reason and existing_reason.casefold() not in {
        reason.casefold() for reason in reasons
    }:
        reasons.append(existing_reason)
    return reasons


def check_escalation(row) -> bool:
    """Return whether a ticket meets a human-intervention escalation trigger."""
    return bool(escalation_reasons(row))


def derive_reason_flags(row):
    flags = escalation_reasons(row)
    resolution = str(row.get("resolution") or "")
    if "KB" not in resolution and "Source:" not in resolution and "knowledge" not in resolution.lower():
        flags.append("KB Missing Context")

    return "; ".join(flags) if flags else "None"


def normalize_resolution_bucket(status: str) -> str:
    value = (status or "").strip().upper()
    if value in {"RESOLVED", "AUTO-RESOLVED", "CLOSED"}:
        return "AI Auto-Resolved"
    if value in {"ESCALATED", "ESCALATED TO JIRA", "NEEDS REVIEW", "REVIEW", "JIRA"}:
        return "Escalated / Human Review"
    return "Other"


def render_kpi_cards(kpis: dict):
    resolution_time = kpis.get("avg_resolution_time_seconds")
    satisfaction = kpis["customer_satisfaction"]
    evaluation = st.session_state.get("dashboard_classifier_eval_summary", {})
    accuracy = evaluation.get("accuracy")
    columns = st.columns(6)
    columns[0].metric("Total Tickets", f"{kpis['total_tickets']:,}")
    columns[1].metric("AI Resolution Rate", f"{kpis['auto_resolution_rate']:.1f}%")
    columns[2].metric(
        "Avg. Resolution Time",
        f"{resolution_time:.2f} sec" if resolution_time is not None else "Not tracked",
    )
    columns[3].metric(
        "Customer Satisfaction",
        f"{satisfaction:.2f}/5" if satisfaction is not None else "Not tracked",
    )
    columns[4].metric(
        "Classification Accuracy",
        f"{accuracy:.1f}%" if accuracy is not None else "Not tracked",
    )
    columns[5].metric("Knowledge Base Coverage", f"{kpis['kb_coverage']:.1f}%")
    st.caption(
        "Resolution time uses recorded ticket creation and resolution timestamps. "
        "Classification accuracy is shown only after a labeled evaluation is run."
    )


def render_charts(frame: pd.DataFrame):
    st.subheader("Ticket Volume and Resolution")
    trend_df = frame.dropna(subset=["created_at"]).copy()
    if not trend_df.empty:
        trend_df["date"] = trend_df["created_at"].dt.floor("D")
        trend_df["is_resolved"] = trend_df["status_upper"].isin(
            {"RESOLVED", "AUTO-RESOLVED", "CLOSED"}
        )
        daily = (
            trend_df.groupby("date")
            .agg(
                **{
                    "Tickets created": ("ticket_id", "size"),
                    "Tickets resolved": ("is_resolved", "sum"),
                }
            )
            .reset_index()
        )
        volume_chart = px.line(
            daily,
            x="date",
            y=["Tickets created", "Tickets resolved"],
            markers=True,
            title="Daily ticket volume and resolved-ticket count",
            template="plotly_white",
        )
    else:
        volume_chart = px.line(
            title="Daily ticket volume and resolved-ticket count"
        )
    st.plotly_chart(volume_chart, width="stretch")
    st.caption(
        "Resolved counts are grouped by ticket creation date because resolution "
        "timestamps are not currently stored."
    )

    category_counts = (
        frame["category"].fillna("Unclassified").value_counts().rename_axis("category").reset_index(name="count")
    )
    if not category_counts.empty:
        category_chart = px.bar(
            category_counts,
            x="count",
            y="category",
            orientation="h",
            title="Ticket volume by category",
            color="count",
            color_continuous_scale="Viridis",
            template="plotly_white",
        )
        category_chart.update_layout(yaxis={"categoryorder": "total ascending"})
    else:
        category_chart = px.bar(title="Ticket volume by category")

    resolved_statuses = {"RESOLVED", "AUTO-RESOLVED", "CLOSED"}
    escalated_statuses = {"ESCALATED", "ESCALATED TO JIRA", "NEEDS REVIEW", "REVIEW", "JIRA"}
    ai_resolved_values = pd.to_numeric(
        frame.get("ai_resolved", pd.Series(index=frame.index, dtype="float64")),
        errors="coerce",
    )
    ai_resolved = (
        ai_resolved_values.eq(1)
        if ai_resolved_values.notna().any()
        else frame["status_upper"].isin(resolved_statuses)
    )
    escalated = (
        pd.to_numeric(frame["escalated"], errors="coerce").fillna(0).eq(1)
        | frame["status_upper"].isin(escalated_statuses)
    )
    resolution_data = pd.DataFrame(
        {
            "outcome": ["AI Resolved", "Escalated"],
            "count": [int(ai_resolved.sum()), int(escalated.sum())],
        }
    )
    resolution_data = resolution_data[resolution_data["count"] > 0]
    resolution_chart = px.pie(
        resolution_data,
        names="outcome",
        values="count",
        title="AI Resolved vs. Escalated Tickets",
        hole=0.45,
        color_discrete_sequence=["#2E6FF2", "#FF8C42"],
    )

    priority_order = ["P1", "P2", "P3", "P4", "UNKNOWN"]
    priority_counts = (
        frame["priority"].str.upper().replace({"": "UNKNOWN"}).value_counts().rename_axis("priority").reset_index(name="count")
    )
    priority_counts["priority"] = priority_counts["priority"].apply(lambda x: x if x in priority_order else "UNKNOWN")
    priority_counts = priority_counts.sort_values("priority", key=lambda s: s.map({p: i for i, p in enumerate(priority_order)}))
    priority_chart = px.bar(
        priority_counts,
        x="count",
        y="priority",
        orientation="h",
        title="Volume by priority level",
        color="count",
        color_continuous_scale="Blues",
        template="plotly_white",
    )
    priority_chart.update_yaxes(
        tickvals=priority_order,
        ticktext=["P1 Critical", "P2 High", "P3 Medium", "P4 Low", "Unknown"],
    )

    left, right = st.columns(2)
    with left:
        st.plotly_chart(category_chart, width="stretch")
    with right:
        st.plotly_chart(priority_chart, width="stretch")

    st.plotly_chart(resolution_chart, width="stretch")


def render_escalation_workflow(frame: pd.DataFrame):
    st.subheader("Escalation Workflow Status")
    total = len(frame)
    classified = int(
        (~frame["category"].str.strip().str.upper().isin({"", "UNCLASSIFIED"})).sum()
    )
    resolution_attempts = int(
        frame["resolution"].fillna("").astype(str).str.strip().ne("").sum()
    )
    review_count = int(
        frame["status_upper"].isin(
            {"ESCALATED", "ESCALATED TO JIRA", "NEEDS REVIEW", "REVIEW", "JIRA"}
        ).sum()
    )
    validated = int(
        frame["status_upper"].isin({"RESOLVED", "AUTO-RESOLVED", "CLOSED"}).sum()
    )
    stages = [
        ("1. AI Classification", classified, f"of {total} tickets classified"),
        ("2. AI Resolution Attempt", resolution_attempts, f"of {total} tickets with a response"),
        ("3. Human Agent Review", review_count, "tickets requiring intervention"),
        ("4. Resolution Validation", validated, "tickets currently resolved"),
    ]
    columns = st.columns(4)
    for column, (label, count, detail) in zip(columns, stages):
        column.metric(label, f"{count:,}")
        column.caption(detail)
    st.caption(
        "Counts are inferred from the current ticket records. The database does "
        "not retain per-stage workflow event history."
    )


def _metric_status(value, target, comparison):
    if value is None:
        return "Not measured"
    met = value > target if comparison == "above" else value < target
    return "On target" if met else "Below target"


def render_optimization_metrics(kpis: dict):
    st.subheader("System Optimization Metrics")
    evaluation = st.session_state.get("dashboard_classifier_eval_summary", {})
    metric_values = [
        (
            "Classification Accuracy",
            evaluation.get("accuracy"),
            ">90%",
            90,
            "above",
            "%",
        ),
        (
            "Resolution Success Rate",
            kpis.get("resolution_success_rate"),
            ">85%",
            85,
            "above",
            "%",
        ),
        (
            "Knowledge Base Coverage",
            kpis.get("kb_coverage"),
            ">90%",
            90,
            "above",
            "%",
        ),
        ("System Uptime", None, "99%", 99, "above", "%"),
        (
            "Avg. AI Response Time",
            kpis.get("avg_ai_response_time"),
            "<5 sec",
            5,
            "below",
            " sec",
        ),
        (
            "User Satisfaction Score",
            kpis.get("customer_satisfaction_pct"),
            ">90%",
            90,
            "above",
            "%",
        ),
    ]

    for row_start in (0, 3):
        columns = st.columns(3)
        for column, (label, value, target, threshold, comparison, unit) in zip(
            columns, metric_values[row_start : row_start + 3]
        ):
            if value is None:
                display_value = "Not tracked"
            elif label == "Avg. AI Response Time" and value < 1:
                display_value = f"{value * 1000:.0f} ms"
            else:
                display_value = f"{value:.1f}{unit}"
            column.metric(label, display_value)
            column.caption(
                f"Target {target} · "
                f"{_metric_status(value, threshold, comparison)}"
            )

    st.caption(
        "Classifier accuracy requires a labeled evaluation CSV. AI response "
        "time uses recorded response-generation durations. System "
        "uptime needs an external uptime monitor and is not inferred from ticket data."
    )


def calculate_classifier_metrics(expected, predicted):
    if len(expected) != len(predicted) or len(expected) == 0:
        raise ValueError("Provide equally sized, non-empty expected and predicted labels.")

    normalized_expected = [str(label).strip().casefold() for label in expected]
    normalized_predicted = [str(label).strip().casefold() for label in predicted]
    if any(not label for label in normalized_expected + normalized_predicted):
        raise ValueError("Classifier labels cannot be empty.")

    return {
        "accuracy": round(
            accuracy_score(normalized_expected, normalized_predicted) * 100, 2
        ),
        "precision": round(
            precision_score(
                normalized_expected,
                normalized_predicted,
                average="weighted",
                zero_division=0,
            )
            * 100,
            2,
        ),
        "recall": round(
            recall_score(
                normalized_expected,
                normalized_predicted,
                average="weighted",
                zero_division=0,
            )
            * 100,
            2,
        ),
    }


def run_escalation_rule_checks():
    agent = EscalationAgent()
    scenarios = [
        (
            "Critical severity escalates",
            {"severity": "Critical"},
            {"valid": True},
            True,
        ),
        (
            "Invalid resolution escalates",
            {"severity": "Low"},
            {"valid": False},
            True,
        ),
        (
            "Valid non-critical resolution does not escalate",
            {"severity": "Medium"},
            {"valid": True},
            False,
        ),
    ]
    results = []
    for name, ticket, validation, expected in scenarios:
        actual = agent.run(ticket, validation)["escalate"]
        results.append({
            "Scenario": name,
            "Expected escalation": expected,
            "Actual escalation": actual,
            "Passed": actual == expected,
        })
    return results


def render_quality_tools():
    with st.expander("Test the AI classifier and escalation rules"):
        st.markdown(
            "Upload a labeled CSV with `text` and `expected_category` columns. "
            "Precision and recall use weighted averages across the supplied labels."
        )
        template = pd.DataFrame(
            {
                "text": ["VPN connection keeps timing out"],
                "expected_category": ["VPN"],
            }
        )
        st.download_button(
            "Download evaluation CSV template",
            template.to_csv(index=False),
            file_name="classifier-evaluation-template.csv",
            mime="text/csv",
            key="dashboard_download_eval_template",
        )
        uploaded_file = st.file_uploader(
            "Labeled classifier test data",
            type=["csv"],
            key="dashboard_classifier_eval_file",
        )
        if st.button("Run AI classifier test", key="dashboard_run_classifier_test"):
            if uploaded_file is None:
                st.error("Upload a labeled CSV before running the classifier test.")
            else:
                try:
                    test_data = pd.read_csv(uploaded_file)
                except (
                    UnicodeDecodeError,
                    pd.errors.ParserError,
                    pd.errors.EmptyDataError,
                ) as error:
                    st.error(f"Could not read the evaluation CSV: {error}")
                else:
                    required = {"text", "expected_category"}
                    missing = required - set(test_data.columns)
                    if missing:
                        st.error(
                            "The evaluation CSV is missing required columns: "
                            + ", ".join(sorted(missing))
                        )
                    elif test_data.empty:
                        st.error("The evaluation CSV contains no test rows.")
                    elif (
                        test_data["text"].isna().any()
                        or test_data["expected_category"].isna().any()
                        or test_data["text"].astype(str).str.strip().eq("").any()
                        or test_data["expected_category"].astype(str).str.strip().eq("").any()
                    ):
                        st.error(
                            "Test text and expected categories must not be blank."
                        )
                    else:
                        try:
                            predicted = [
                                process_ticket(str(text))["category"]
                                for text in test_data["text"]
                            ]
                        except FileNotFoundError:
                            st.error(
                                "The classifier model is missing. Train it with "
                                "`python train_model.py`, then retry."
                            )
                        else:
                            expected = test_data["expected_category"].astype(str).tolist()
                            try:
                                metrics = calculate_classifier_metrics(
                                    expected, predicted
                                )
                            except ValueError as error:
                                st.error(str(error))
                            else:
                                st.session_state[
                                    "dashboard_classifier_eval_summary"
                                ] = metrics
                                st.session_state[
                                    "dashboard_classifier_eval_rows"
                                ] = test_data.assign(predicted_category=predicted)
                                logger.info(
                                    "classifier_evaluation_completed rows=%s accuracy_pct=%.2f precision_pct=%.2f recall_pct=%.2f",
                                    len(test_data),
                                    metrics["accuracy"],
                                    metrics["precision"],
                                    metrics["recall"],
                                )

        evaluation = st.session_state.get("dashboard_classifier_eval_summary")
        if evaluation:
            columns = st.columns(3)
            columns[0].metric("Accuracy", f"{evaluation['accuracy']:.2f}%")
            columns[1].metric("Weighted Precision", f"{evaluation['precision']:.2f}%")
            columns[2].metric("Weighted Recall", f"{evaluation['recall']:.2f}%")
            st.dataframe(
                st.session_state["dashboard_classifier_eval_rows"],
                hide_index=True,
                width="stretch",
            )

        if st.button(
            "Test escalation rules",
            key="dashboard_test_escalation_rules",
        ):
            results = run_escalation_rule_checks()
            st.session_state["dashboard_escalation_test_results"] = results
            logger.info(
                "escalation_rule_checks_completed passed=%s total=%s",
                sum(result["Passed"] for result in results),
                len(results),
            )
        if "dashboard_escalation_test_results" in st.session_state:
            st.dataframe(
                pd.DataFrame(st.session_state["dashboard_escalation_test_results"]),
                hide_index=True,
                width="stretch",
            )


def render_satisfaction_feedback(frame: pd.DataFrame):
    resolved = frame[
        frame["status_upper"].isin({"RESOLVED", "AUTO-RESOLVED", "CLOSED"})
    ]
    if resolved.empty:
        return

    with st.expander("Record user satisfaction feedback"):
        options = resolved["ticket_id"].tolist()
        ticket_id = st.selectbox(
            "Resolved ticket",
            options,
            format_func=lambda value: (
                f"#{value} - "
                f"{resolved.loc[resolved['ticket_id'] == value, 'title'].iloc[0]}"
            ),
            key="dashboard_csat_ticket",
        )
        score = st.slider(
            "User satisfaction score",
            min_value=1,
            max_value=5,
            value=5,
            key="dashboard_csat_score",
        )
        if st.button("Save satisfaction score", key="dashboard_save_csat"):
            update_ticket(int(ticket_id), csat=score)
            load_ticket_data.clear()
            logger.info(
                "ticket_satisfaction_recorded ticket_id=%s score=%s",
                ticket_id,
                score,
            )
            st.session_state["dashboard_notice"] = (
                f"Saved satisfaction feedback for ticket #{ticket_id}."
            )
            st.rerun()


def render_escalation_monitor(frame: pd.DataFrame):
    st.subheader("Human Intervention Monitor")
    st.caption(
        "Critical tickets, low-confidence classifications, failed resolutions, "
        "and customer requests for human support."
    )

    resolved_statuses = {"RESOLVED", "AUTO-RESOLVED", "CLOSED"}
    intervention = frame[
        frame["requires_human_review"]
        & ~frame["status_upper"].isin(resolved_statuses)
    ].copy()
    if intervention.empty:
        st.success("No tickets currently require human intervention.")
        return

    intervention = intervention.sort_values(
        "ticket_id", ascending=False
    ).reset_index(drop=True)
    for _, ticket in intervention.iterrows():
        st.warning(
            f"Ticket #{ticket['ticket_id']} - {ticket['title']}: "
            f"{ticket['intervention_reasons']}"
        )

    filter_category, filter_priority, filter_severity = st.columns(3)
    category_options = sorted(intervention["category"].dropna().unique().tolist())
    priority_options = sorted(intervention["priority"].dropna().unique().tolist())
    severity_options = sorted(intervention["severity"].dropna().unique().tolist())

    category_filter = filter_category.multiselect(
        "Category",
        category_options,
        default=category_options,
        key="dashboard_category_filter",
    )
    priority_filter = filter_priority.multiselect(
        "Priority",
        priority_options,
        default=priority_options,
        key="dashboard_priority_filter",
    )
    severity_filter = filter_severity.multiselect(
        "Severity",
        severity_options,
        default=severity_options,
        key="dashboard_severity_filter",
    )

    intervention = intervention[
        intervention["category"].isin(category_filter)
        & intervention["priority"].isin(priority_filter)
        & intervention["severity"].isin(severity_filter)
    ]

    display_columns = [
        "ticket_id",
        "employee_name",
        "title",
        "category",
        "priority",
        "severity",
        "confidence",
        "status",
        "intervention_reasons",
        "reason_flags",
    ]
    st.dataframe(
        intervention[display_columns],
        hide_index=True,
        width="stretch",
        column_config={
            "confidence": st.column_config.NumberColumn("Confidence", format="%.1f%%"),
            "intervention_reasons": st.column_config.TextColumn(
                "Intervention reasons", width="large"
            ),
            "reason_flags": st.column_config.TextColumn("Reason flags", width="large"),
        },
    )

    if intervention.empty:
        st.info("No escalated tickets match the selected filters.")
        return

    selected_ticket_id = st.selectbox(
        "Choose a ticket for details or resolution",
        intervention["ticket_id"].tolist(),
        format_func=lambda ticket_id: (
            f"#{ticket_id} - "
            f"{intervention.loc[intervention['ticket_id'] == ticket_id, 'title'].iloc[0]}"
        ),
        key="dashboard_escalated_ticket",
    )
    row = intervention.loc[intervention["ticket_id"] == selected_ticket_id].iloc[0]
    with st.expander("View ticket logs"):
        st.json(
            {
                "ticket_id": row["ticket_id"],
                "employee_name": row["employee_name"],
                "title": row["title"],
                "category": row["category"],
                "priority": row["priority"],
                "severity": row["severity"],
                "confidence": row["confidence"],
                "status": row["status"],
                "description": row["description"],
                "resolution": row["resolution"],
                "created_at": str(row["created_at"]),
            }
        )

    if st.button("Mark as Resolved", key=f"resolve_{selected_ticket_id}"):
        update_ticket(int(selected_ticket_id), status="Resolved")
        load_ticket_data.clear()
        logger.info("ticket_marked_resolved ticket_id=%s source=dashboard", selected_ticket_id)
        st.session_state["dashboard_notice"] = f"Ticket #{selected_ticket_id} marked as resolved."
        st.rerun()


@st.fragment(run_every="30s")
def render_dashboard():
    st.title("Dashboard and Optimization")
    st.caption(
        "SupportPilot ticket performance, AI quality, response-time monitoring, "
        "and escalation workflow."
    )

    if st.button("Start Over", key="dashboard_start_over"):
        reset_keys = [
            "dashboard_category_filter",
            "dashboard_priority_filter",
            "dashboard_severity_filter",
            "dashboard_escalated_ticket",
            "dashboard_csat_ticket",
            "dashboard_csat_score",
            "dashboard_classifier_eval_file",
            "dashboard_classifier_eval_summary",
            "dashboard_classifier_eval_rows",
            "dashboard_escalation_test_results",
        ]
        for key in reset_keys:
            st.session_state.pop(key, None)
        load_ticket_data.clear()
        logger.info("dashboard_state_reset")
        st.session_state["dashboard_notice"] = (
            "Dashboard filters and selections were reset. Ticket data was not changed."
        )
        st.rerun()

    notice = st.session_state.pop("dashboard_notice", None)
    if notice:
        st.success(notice)

    ensure_database_initialized()
    frame = build_dashboard_frame(load_ticket_data())

    if frame.empty:
        st.info(
            "No ticket data was found in the SQLite database yet. Submit tickets "
            "through SupportPilot to populate metrics."
        )

    kpis = calculate_kpis(frame)
    render_kpi_cards(kpis)

    st.markdown("---")
    render_optimization_metrics(kpis)

    st.markdown("---")
    render_charts(frame)

    st.markdown("---")
    render_escalation_workflow(frame)


    st.markdown("---")
    render_quality_tools()
    render_satisfaction_feedback(frame)

    st.markdown("---")
    render_escalation_monitor(frame)


def main():
    if st.sidebar.button("Refresh dashboard data", key="dashboard_refresh"):
        load_ticket_data.clear()
        logger.info("dashboard_data_refreshed")
        st.rerun()
    render_dashboard()


if __name__ == "__main__":
    main()
