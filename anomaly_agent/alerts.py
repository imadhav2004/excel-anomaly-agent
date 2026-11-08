"""Alert rules: check them against the scan result and write the alert e-mail.

No Streamlit and no database here, only rules, so everything can be tested directly.
A rule is a plain dict: name, metric (None = any metric), min_severity, min_votes, direction, active.
A "row" is one line of the scan summary (see detection.engine.summarise).
"""

SEVERITIES = ["LOW", "MEDIUM", "HIGH"]
RANK = {name: number for number, name in enumerate(SEVERITIES, start=1)}
DIRECTIONS = ["any", "up", "down"]
SCOPES = {
    "Latest period only": 1,
    "Last 3 periods": 3,
    "Every period in the file": None,
}
MAX_RULES = 20
MAX_NAME = 60
EMAIL_LIST_LIMIT = 20


class RuleError(Exception):
    """A rule the person typed is not valid. The message is shown on the page."""


def clean_rule(name, metric, min_severity, min_votes, direction):
    """Check the form values and return a clean rule dict, or raise RuleError."""
    name = " ".join((name or "").split())
    if not name:
        raise RuleError("Please give the rule a name.")
    if len(name) > MAX_NAME:
        raise RuleError(f"The rule name can have at most {MAX_NAME} characters.")
    if min_severity not in RANK:
        raise RuleError("Choose LOW, MEDIUM or HIGH as the minimum severity.")
    try:
        min_votes = int(min_votes)
    except (TypeError, ValueError):
        raise RuleError("The number of agreeing methods must be a whole number.") from None
    if not 1 <= min_votes <= 6:
        raise RuleError("The number of agreeing methods must be between 1 and 6.")
    if direction not in DIRECTIONS:
        raise RuleError("Choose any, up or down as the direction.")
    metric = (metric or "").strip() or None
    if metric is not None and len(metric) > 100:
        raise RuleError("The metric name is too long.")
    return {"name": name, "metric": metric, "min_severity": min_severity, "min_votes": min_votes, "direction": direction}


def describe_rule(rule):
    where = rule["metric"] or "any metric"
    way = {"any": "", "up": ", only increases", "down": ", only decreases"}[rule["direction"]]
    methods = "1 method" if rule["min_votes"] == 1 else f"{rule['min_votes']} methods"
    return f"{where}: {rule['min_severity']} or worse, at least {methods} agree{way}"


def rule_matches(rule, row):
    if not rule.get("active", True):
        return False
    if rule["metric"] is not None and rule["metric"] != row["metric"]:
        return False
    if RANK[row["severity"]] < RANK[rule["min_severity"]]:
        return False
    if row["votes"] < rule["min_votes"]:
        return False
    return rule["direction"] == "any" or rule["direction"] == row["direction"]


def periods_in_scope(dates, scope_periods):
    """The dates an alert may be about: the newest `scope_periods` dates, or all when it is None."""
    ordered = sorted(set(dates))
    return set(ordered if scope_periods is None else ordered[-scope_periods:])


def evaluate_rules(rules, summary, dates, scope_periods=1):
    """Every (rule, row) pair that matches, for rows inside the chosen scope."""
    allowed = periods_in_scope(dates, scope_periods)
    return [
        {"rule": rule, "row": row}
        for rule in rules
        for row in summary
        if row["period"] in allowed and rule_matches(rule, row)
    ]


def alert_message(rule_name, row):
    change = row["deviation_pct"]
    size = "" if change is None else f" {change:+.0%}"
    return (
        f"{row['metric']} went {row['direction']}{size} in {row['period'].strftime('%b %Y')}: "
        f"{row['severity']}, {row['votes']} of {row['methods_run']} methods agree (rule: {rule_name})"
    )


def build_alert_email(user_name, source_name, events):
    """Subject and body for the e-mail about NEW alerts."""
    count = len(events)
    subject = f"[Excel Anomaly Agent] {count} new alert{'s' if count != 1 else ''} in {source_name}"
    lines = [f"Hello {user_name},", "", f"Your alert rules found {count} new alert(s) in {source_name}:", ""]
    for event in events[:EMAIL_LIST_LIMIT]:
        lines.append(f"- [{event['severity']}] {event['message']}")
    if count > EMAIL_LIST_LIMIT:
        lines.append(f"... and {count - EMAIL_LIST_LIMIT} more. Open the Alerts page to see all of them.")
    lines += ["", "These are statistical alerts, not confirmed business problems."]
    return subject, "\n".join(lines)
