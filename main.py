import logging

from anomaly_agent.ai_explainer import get_explanations
from anomaly_agent.emailer import send_email
from anomaly_agent.history import filter_new_anomalies, mark_alerted, save_analysis
from anomaly_agent.latest import latest_period_anomalies
from anomaly_agent.loader import load_data
from anomaly_agent.report import build_email
from anomaly_agent.validator import DataError

FILE_PATH = "data/sample_sales.xlsx"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        df = load_data(FILE_PATH)
    except DataError as error:
        print(f"Cannot analyse this file: {error}")
        return

    period = df["Month"].iloc[-1].strftime("%b %Y")
    anomalies = latest_period_anomalies(df, "Month")  # the same scan as the web page
    save_analysis(FILE_PATH, period, len(df), anomalies)

    if not anomalies:
        print(f"No anomalies found for {period}. No email needed.")
        return

    new_anomalies = filter_new_anomalies(anomalies, FILE_PATH, period)
    if not new_anomalies:
        print(f"All alerts for {period} were already sent. No email needed.")
        return

    explanations = get_explanations(new_anomalies, period)
    subject, body = build_email(new_anomalies, period, explanations)
    if send_email(subject, body):
        mark_alerted(new_anomalies, FILE_PATH, period)


if __name__ == "__main__":
    main()
