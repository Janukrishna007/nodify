"""Confirmed visual-evidence alerts and optional SMTP delivery."""
from datetime import datetime, timezone
from email.message import EmailMessage
import os
import smtplib
from uuid import uuid4

from scoring import SUPPORTED_CLASSES


def intensity_level(risk):
    return "critical" if risk >= 0.85 else "high" if risk >= 0.65 else "moderate" if risk >= 0.35 else "low"


def email_configured():
    return all(os.environ.get(key) for key in ("ALERT_SMTP_HOST", "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO"))


def send_email_alert(alert, filename):
    """Send one alert. Credentials are read only from the process environment."""
    if not email_configured():
        return "not_configured"
    message = EmailMessage()
    message["Subject"] = f"[{alert['severity'].upper()}] DisasterVision {alert['type']} alert"
    message["From"] = os.environ["ALERT_EMAIL_FROM"]
    message["To"] = os.environ["ALERT_EMAIL_TO"]
    message.set_content(
        f"{alert['message']}\n\nVideo: {filename}\nFrame: {alert['frameNumber']}\n"
        f"Confidence: {alert['confidence']:.1%}\nRisk index: {alert['risk']:.1%}\n"
        f"Tracked regions: {', '.join(alert['trackIds']) or 'unassigned'}\n\n"
        "This is an automated visual model alert. Confirm conditions before dispatching responders."
    )
    use_ssl = os.environ.get("ALERT_SMTP_SSL", "false").lower() in {"1", "true", "yes"}
    client_type = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with client_type(os.environ["ALERT_SMTP_HOST"], int(os.environ.get("ALERT_SMTP_PORT", "587")), timeout=15) as client:
        if not use_ssl:
            client.starttls()
        if username := os.environ.get("ALERT_SMTP_USERNAME"):
            client.login(username, os.environ.get("ALERT_SMTP_PASSWORD", ""))
        client.send_message(message)
    return "sent"


class AlertEngine:
    def __init__(self, min_confidence=0.6, min_risk=0.5, persistence=3, cooldown=60):
        self.min_confidence = min_confidence
        self.min_risk = min_risk
        self.persistence = persistence
        self.cooldown = cooldown
        self.streak = dict.fromkeys(SUPPORTED_CLASSES, 0)
        self.previous = {}

    def update(self, detections, cells, timestamp, frame_number, session_id):
        events = []
        for name in SUPPORTED_CLASSES:
            evidence = [d for d in detections if d.class_name == name and d.confidence >= self.min_confidence]
            self.streak[name] = self.streak[name] + 1 if evidence else 0
            risk = max((c["byClass"][name]["score"] / (1 + c["byClass"][name]["score"]) for c in cells), default=0)
            severity = intensity_level(risk)
            previous = self.previous.get(name)
            escalated = previous and ["low", "moderate", "high", "critical"].index(severity) > previous[1]
            if self.streak[name] < self.persistence or risk < self.min_risk:
                continue
            if previous and timestamp - previous[0] < self.cooldown and not escalated:
                continue
            self.previous[name] = (timestamp, ["low", "moderate", "high", "critical"].index(severity))
            events.append({"id": uuid4().hex, "sessionId": session_id, "type": name,
                           "severity": severity, "risk": round(risk, 6),
                           "confidence": round(max(d.confidence for d in evidence), 6),
                           "timestamp": timestamp, "frameNumber": frame_number,
                           "trackIds": sorted({d.track_id for d in evidence if d.track_id}),
                           "createdAt": datetime.now(timezone.utc).isoformat(), "acknowledgedAt": None,
                           "emailStatus": "pending" if email_configured() else "not_configured",
                           "message": f"{name.title()} detected: {severity} visual intensity at {timestamp:.1f}s."})
        return events
