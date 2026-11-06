const dashboardError = document.getElementById("dashboardError");
const chartContainer = document.getElementById("ticketChart");

function hasNumber(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

function formatPercent(value) {
    return hasNumber(value) ? `${Number(value).toFixed(1)}%` : "Not tracked";
}

function formatDuration(seconds) {
    if (!hasNumber(seconds)) return "Not tracked";
    const value = Number(seconds);
    if (value < 60) return `${value.toFixed(1)} sec`;
    return `${(value / 60).toFixed(1)} min`;
}

function setProgress(id, value, max = 100) {
    const bar = document.getElementById(id);
    if (!bar || !hasNumber(value)) return;
    bar.value = Math.min(max, Math.max(0, Number(value)));
}

function renderClassifier(evaluation) {
    const valueOrNA = (value) => hasNumber(value) ? `${Number(value).toFixed(1)}%` : "N/A";
    document.getElementById("classifierAccuracy").textContent = valueOrNA(evaluation?.accuracy);
    document.getElementById("classifierPrecision").textContent = valueOrNA(evaluation?.precision);
    document.getElementById("classifierRecall").textContent = valueOrNA(evaluation?.recall);
    document.getElementById("classifierF1").textContent = valueOrNA(evaluation?.f1_score);
    document.getElementById("classifierDataset").textContent = evaluation
        ? `${evaluation.samples} isolated test samples · not production tickets`
        : "Classifier evaluation is unavailable. Check the model and retry.";
}

function renderMetrics(metrics, evaluation) {
    document.getElementById("kpiTotalTickets").textContent = metrics.total_tickets ?? 0;
    document.getElementById("kpiTicketsToday").textContent = metrics.total_tickets_today ?? 0;
    document.getElementById("kpiResolutionRate").textContent = formatPercent(metrics.ai_resolution_rate);


    const resolutionSamples = Number(metrics.resolution_time_samples) || 0;
    const unresolvedTiming = Number(metrics.resolved_without_timing) || 0;
    document.getElementById("kpiResolutionTime").textContent = hasNumber(metrics.average_resolution_time_seconds)
        ? formatDuration(metrics.average_resolution_time_seconds)
        : "<5 sec";
    document.getElementById("resolutionTimeNote").textContent = resolutionSamples
        ? `Target: below 5 sec · Average across ${resolutionSamples} resolved ticket${resolutionSamples === 1 ? "" : "s"}`
        : unresolvedTiming
            ? `Target only · No timing data for ${unresolvedTiming} older resolved ticket${unresolvedTiming === 1 ? "" : "s"}`
            : "Target only · No resolved tickets to measure yet";
    document.getElementById("kpiSatisfaction").textContent = hasNumber(metrics.user_satisfaction)
        ? `${Number(metrics.user_satisfaction).toFixed(1)} / 5`
        : "Not tracked";

    const dailyChange = metrics.tickets_today_change_pct;
    document.getElementById("ticketsTodayChange").textContent = dailyChange === null
        ? "No previous-day baseline"
        : `${dailyChange > 0 ? "+" : ""}${Number(dailyChange).toFixed(1)}% vs yesterday`;

    const accuracy = evaluation?.accuracy ?? metrics.classification_accuracy;
    document.getElementById("optAccuracy").textContent = formatPercent(accuracy);
    document.getElementById("optResolution").textContent = formatPercent(metrics.resolution_success_rate);
    document.getElementById("optCoverage").textContent = formatPercent(metrics.knowledge_base_coverage);
    document.getElementById("optUptime").textContent = "Online";
    document.getElementById("uptimeDetail").textContent = `Running ${formatDuration(metrics.system_uptime_seconds)}`;
    document.getElementById("optResponseTime").textContent = formatDuration(metrics.average_response_time_seconds);
    document.getElementById("optSatisfaction").textContent = hasNumber(metrics.user_satisfaction)
        ? `${Number(metrics.user_satisfaction).toFixed(1)} / 5`
        : "Not tracked";

    setProgress("barAccuracy", accuracy);
    setProgress("barResolution", metrics.resolution_success_rate);
    setProgress("barCoverage", metrics.knowledge_base_coverage);
    setProgress("barResponseTime", metrics.average_response_time_seconds, 5);
    setProgress("barSatisfaction", Number(metrics.user_satisfaction) * 20);

    document.getElementById("monitorApiTime").textContent = hasNumber(metrics.average_api_response_ms)
        ? `${Number(metrics.average_api_response_ms).toFixed(0)} ms` : "Not tracked";
    document.getElementById("monitorAiTime").textContent = formatDuration(metrics.average_response_time_seconds);
    document.getElementById("monitorErrorRate").textContent = formatPercent(metrics.api_error_rate);
    document.getElementById("monitorResolutionRate").textContent = formatPercent(metrics.resolution_success_rate);
    document.getElementById("monitorEscalationRate").textContent = formatPercent(metrics.escalation_rate);
    document.getElementById("monitorAccuracy").textContent = formatPercent(accuracy);
    document.getElementById("monitorSuccessfulResponses").textContent = metrics.successful_responses ?? 0;
    document.getElementById("monitorFailedResponses").textContent = metrics.failed_responses ?? 0;
    renderClassifier(evaluation);
}

function appendSvg(parent, name, attributes = {}) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    parent.appendChild(element);
    return element;
}

function renderChart(days) {
    chartContainer.replaceChildren();
    if (!Array.isArray(days) || days.length === 0 || days.every((day) => !day.received && !day.resolved)) {
        const empty = document.createElement("div");
        empty.className = "chart-empty";
        empty.textContent = "No ticket activity recorded this week.";
        chartContainer.appendChild(empty);
        return;
    }

    const width = 800;
    const height = 250;
    const margins = { left: 42, right: 18, top: 14, bottom: 34 };
    const plotWidth = width - margins.left - margins.right;
    const plotHeight = height - margins.top - margins.bottom;
    const maxValue = Math.max(1, ...days.map((day) => Math.max(Number(day.received) || 0, Number(day.resolved) || 0)));
    const xAt = (index) => margins.left + (days.length < 2 ? plotWidth / 2 : (index / (days.length - 1)) * plotWidth);
    const yAt = (value) => margins.top + plotHeight - ((Number(value) || 0) / maxValue) * plotHeight;
    const svg = appendSvg(chartContainer, "svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Tickets received and resolved this week" });

    for (let line = 0; line <= 3; line += 1) {
        const y = margins.top + (plotHeight / 3) * line;
        appendSvg(svg, "line", { x1: margins.left, x2: width - margins.right, y1: y, y2: y, class: "chart-gridline" });
        const label = appendSvg(svg, "text", { x: margins.left - 10, y: y + 4, "text-anchor": "end", class: "chart-axis-label" });
        label.textContent = Math.round(maxValue * (1 - line / 3));
    }

    const series = [
        { key: "received", lineClass: "chart-line-received", areaClass: "chart-area-received", dotClass: "chart-dot-received" },
        { key: "resolved", lineClass: "chart-line-resolved", areaClass: "chart-area-resolved", dotClass: "chart-dot-resolved" },
    ];
    series.forEach(({ key, lineClass, areaClass, dotClass }) => {
        const points = days.map((day, index) => [xAt(index), yAt(day[key])]);
        const linePath = points.map(([x, y], index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
        const areaPath = `${linePath} L${xAt(days.length - 1)},${margins.top + plotHeight} L${xAt(0)},${margins.top + plotHeight} Z`;
        appendSvg(svg, "path", { d: areaPath, class: areaClass });
        appendSvg(svg, "path", { d: linePath, class: lineClass });
        points.forEach(([x, y]) => appendSvg(svg, "circle", { cx: x, cy: y, r: 4, class: dotClass }));
    });

    days.forEach((day, index) => {
        const label = appendSvg(svg, "text", { x: xAt(index), y: height - 10, "text-anchor": "middle", class: "chart-axis-label" });
        label.textContent = day.day.slice(0, 3);
    });
}

async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.message || "Dashboard request failed.");
    return data;
}

async function loadDashboard() {
    dashboardError.hidden = true;
    chartContainer.innerHTML = '<div class="chart-loading">Loading ticket activity...</div>';
    try {
        const [metricsResult, chartResult, workflowResult] = await Promise.all([
            fetchJson("/api/dashboard/metrics/"),
            fetchJson("/api/dashboard/chart/"),
            fetchJson("/api/dashboard/escalation/"),
        ]);
        renderMetrics(metricsResult.metrics, metricsResult.classifier_evaluation);
        renderChart(chartResult.days);
        const periodStart = new Date(`${chartResult.period_start}T00:00:00`);
        const periodEnd = new Date(periodStart);
        periodEnd.setDate(periodEnd.getDate() + 6);
        const periodLabel = new Intl.DateTimeFormat(undefined, {
            month: "short", day: "numeric",
        });
        document.getElementById("chartPeriod").textContent =
            `${chartResult.uses_latest_activity_week ? "Latest active week" : "This week"}: ` +
            `${periodLabel.format(periodStart)}–${periodLabel.format(periodEnd)}`;
        document.getElementById("chartDataNote").textContent =
            chartResult.legacy_resolution_date_fallbacks
                ? `${chartResult.legacy_resolution_date_fallbacks} older resolved tickets have no resolution timestamp; they are grouped by ticket date.`
                : "Resolution counts use recorded resolution dates.";
        document.getElementById("workflowClassified").textContent = workflowResult.workflow.classified;
        document.getElementById("workflowResolved").textContent = workflowResult.workflow.automatically_resolved;
        document.getElementById("workflowEscalated").textContent = workflowResult.workflow.escalated;
        document.getElementById("workflowValidation").textContent = workflowResult.workflow.waiting_validation;
    } catch (error) {
        chartContainer.replaceChildren();
        dashboardError.hidden = false;
        console.error("Dashboard refresh failed", error);
    }
}

async function runClassifierTest() {
    const button = document.getElementById("runClassifierTest");
    button.disabled = true;
    button.textContent = "Testing...";
    try {
        const result = await fetchJson("/api/dashboard/classifier-evaluation/");
        renderClassifier(result.evaluation);
    } catch (error) {
        document.getElementById("classifierDataset").textContent = "Classifier test failed. Check the model and retry.";
        console.error("Classifier evaluation failed", error);
    } finally {
        button.disabled = false;
        button.textContent = "Run test";
    }
}

document.getElementById("refreshDashboard").addEventListener("click", loadDashboard);
document.getElementById("retryDashboard").addEventListener("click", loadDashboard);
document.getElementById("runClassifierTest").addEventListener("click", runClassifierTest);
loadDashboard();
window.setInterval(() => {
    if (!document.hidden) loadDashboard();
}, 30000);