# Design Document: Excel Anomaly Agent

## 1. Problem
People look at spreadsheets late, or never. A sudden jump or drop in revenue or returns can sit unnoticed. The agent checks the sheet and speaks up only when needed.

## 2. Flow

```
Excel file -> validator -> loader -> detector -> report -> (AI explainer) -> history filter -> emailer
                                          |                                      |
                                          +-> exporter (Excel) / pdf_report      +-> SQLite
```

main.py and app.py are two front doors to the same pipeline.

## 3. Modules

| Module | Job |
|---|---|
| validator | file size/extension, minimum rows, raises DataError with a friendly message |
| loader | reads Excel, parses the date column, sorts |
| detector | percent change, z-score, severity |
| report | business context text, email body, table rows |
| ai_explainer | one Gemini request, JSON reply, falls back to built-in sentences |
| history | SQLite: analyses, anomalies, alerts_sent; avoids repeated alerts |
| emailer | Gmail SMTP_SSL 465; returns True only if really sent |
| exporter / pdf_report | downloadable reports |

## 4. Key decisions and why

- **Two signals (pct change and z-score):** pct alone flags small noisy metrics; z alone misses sudden moves on steady data.
- **Dry-run default:** a beginner mistake should not spam a real inbox.
- **Custom DataError:** user mistakes get a clear message, not a traceback.
- **AI is optional and last:** detection is plain maths (testable, repeatable). AI only words the explanation and is labelled "AI suggestion".
- **Minimal data to AI:** only flagged numbers are sent.
- **Alert marked only after a real send:** a failed or dry-run send can be retried.
- **Public demo mode:** a public site would share one history DB across visitors and spend the owner's AI quota, so AI/history/saving are off there.
- **Secrets:** `.env` locally, Streamlit Secrets online; never in git.

## 5. Testing
47 pytest tests cover detector, loader, validator, report, history, exporter, main, AI explainer (API never called: conftest removes the key) and PDF. The dashboard was checked with Streamlit AppTest and a screenshot.

## 6. Limits and future work
- Latest-row comparison only; no seasonality.
- SQLite is single-user and temporary on free hosting.
- Possible next steps: scheduled runs, Slack alerts, per-metric thresholds, multiple sheets.
