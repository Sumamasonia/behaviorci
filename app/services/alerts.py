"""
Alerting Service.

Sends a notification when the regression diff engine finds a problem.
Both Slack and email are optional -- if their env vars aren't set, alerts
are silently skipped, nothing breaks.
"""
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import settings


def _format_regression_summary(suite_name: str, run_number: int, report: dict) -> str:
    lines = [f"BehaviorCI regression detected: '{suite_name}' run #{run_number}"]

    if report.get("pass_fail_flips"):
        lines.append(f"\n{len(report['pass_fail_flips'])} test case(s) flipped from pass to fail:")
        for f in report["pass_fail_flips"][:5]:
            lines.append(f"  - {f['test_case_name']}")

    if report.get("metric_regressions"):
        lines.append(f"\n{len(report['metric_regressions'])} metric regression(s):")
        for m in report["metric_regressions"][:5]:
            lines.append(f"  - {m['test_case_name']}: {m['dimension']} dropped {m['previous_score']} -> {m['current_score']}")

    if report.get("systemic_patterns"):
        lines.append("\nSystemic patterns:")
        for p in report["systemic_patterns"]:
            lines.append(f"  - tag '{p['tag']}': {p['degraded']}/{p['total']} cases degraded ({round(p['degradation_rate']*100)}%)")

    return "\n".join(lines)


def send_slack_alert(suite_name: str, run_number: int, run_id: str, report: dict) -> bool:
    if not settings.slack_webhook_url:
        return False

    summary = _format_regression_summary(suite_name, run_number, report)
    payload = {
        "text": summary,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{summary.splitlines()[0]}*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "```" + "\n".join(summary.splitlines()[1:]) + "```"}},
        ],
    }
    try:
        resp = httpx.post(settings.slack_webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[BehaviorCI] Slack alert failed to send: {e}")
        return False


def send_email_alert(suite_name: str, run_number: int, run_id: str, report: dict) -> bool:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.alert_email_to):
        return False

    summary = _format_regression_summary(suite_name, run_number, report)
    msg = MIMEText(summary)
    msg["Subject"] = f"[BehaviorCI] Regression detected: {suite_name} run #{run_number}"
    msg["From"] = settings.smtp_user
    msg["To"] = settings.alert_email_to

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, [settings.alert_email_to], msg.as_string())
        return True
    except Exception as e:
        print(f"[BehaviorCI] Email alert failed to send: {e}")
        return False


def send_regression_alerts(suite_name: str, run_number: int, run_id: str, report: dict) -> dict:
    if not report.get("has_regressions"):
        return {"slack": False, "email": False}

    return {
        "slack": send_slack_alert(suite_name, run_number, run_id, report),
        "email": send_email_alert(suite_name, run_number, run_id, report),
    }