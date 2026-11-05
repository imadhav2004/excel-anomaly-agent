# Why each change might matter. Version 1 uses fixed sentences; AI text comes later.
CONTEXT = {
    "Revenue": {
        "up": "Sales income rose sharply. Check for a big order, a price change or a promotion.",
        "down": "Sales income fell sharply. Check for lost customers, stock problems or a tracking error.",
    },
    "Orders": {
        "up": "Order volume jumped. Make sure stock and delivery can keep up.",
        "down": "Order volume dropped. Check the website, the ads and the competition.",
    },
    "Returns": {
        "up": "More products are coming back. Check product quality or delivery damage.",
        "down": "Returns fell sharply. This is usually good, but confirm the data is complete.",
    },
    "Ad_Spend": {
        "up": "Advertising cost jumped. Check that the extra spend is bringing results.",
        "down": "Advertising cost dropped. Check whether campaigns stopped by mistake.",
    },
    "Website_Visits": {
        "up": "Website traffic surged. Check where the visitors came from.",
        "down": "Website traffic fell. Check for site problems or ended campaigns.",
    },
    "Sales": {
        "up": "Sales rose sharply. Check for a big order, a price change or a promotion.",
        "down": "Sales fell sharply. Check for lost customers, stock problems or a tracking error.",
    },
    "Customers": {
        "up": "The number of customers jumped. Check whether a campaign or a data import caused it.",
        "down": "The number of customers dropped. Check for lost accounts or missing data.",
    },
    "Refunds": {
        "up": "Refunds rose sharply. Check product quality, delivery problems or a billing mistake.",
        "down": "Refunds fell sharply. This is usually good, but confirm the data is complete.",
    },
    "Marketing": {
        "up": "Marketing cost jumped. Check that the extra spend is bringing results.",
        "down": "Marketing cost dropped. Check whether campaigns stopped by mistake.",
    },
}

GENERIC = {
    "up": "This metric rose unusually. Check whether the cause is real or a data entry mistake.",
    "down": "This metric fell unusually. Check whether the cause is real or a data entry mistake.",
}


def describe_change(anomaly):
    if anomaly["pct_change"] is None:
        return f"went {anomaly['direction']} from zero"
    return f"went {anomaly['direction']} {abs(anomaly['pct_change']):.0%}"


def build_email(anomalies, period, explanations=None):
    high_count = sum(1 for a in anomalies if a["severity"] == "HIGH")
    subject = f"Anomaly alert for {period}: {len(anomalies)} metric(s) flagged, {high_count} HIGH"

    explanations = explanations or {}
    used_ai = False

    lines = [f"Anomalies found for {period}:", ""]
    for a in anomalies:
        lines.append(
            f"[{a['severity']}] {a['metric']} {describe_change(a)} "
            f"({a['previous']:,.0f} -> {a['latest']:,.0f}, z-score {a['z_score']:.1f})"
        )
        item = explanations.get(a["metric"])
        if item and item["source"] == "AI":
            label = "Why it matters (AI suggestion)"
            note = item["text"]
            used_ai = True
        else:
            label = "Why it matters"
            note = item["text"] if item else CONTEXT.get(a["metric"], GENERIC)[a["direction"]]
        lines.append(f"    {label}: {note}")
        lines.append("")

    lines.append(
        "These are statistical alerts, not confirmed business problems. "
        "Please check the data before acting."
    )
    if used_ai:
        lines.append("AI suggestions are possibilities, not facts.")
    return subject, "\n".join(lines)


def anomalies_to_rows(anomalies):
    """One simple record per anomaly (HIGH first). Used by the dashboard and the Excel report."""
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows = []
    for a in sorted(anomalies, key=lambda a: order[a["severity"]]):
        rows.append(
            {
                "Metric": a["metric"],
                "Severity": a["severity"],
                "Change": describe_change(a),
                "Previous": a["previous"],
                "Latest": a["latest"],
                "Z-score": round(a["z_score"], 1),
            }
        )
    return rows
