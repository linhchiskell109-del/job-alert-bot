"""Gửi email thông báo job mới — nhóm theo company, hiển thị title/location/
department (nếu có)/link. Gửi cả bản HTML (đẹp) lẫn plain text (fallback)."""
import os
import smtplib
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _group_by_company(jobs: list[dict]) -> dict:
    grouped = defaultdict(list)
    for j in jobs:
        grouped[j["company"]].append(j)
    return dict(grouped)


def _build_plain_text(grouped: dict) -> str:
    lines = []
    for company, jobs in grouped.items():
        lines.append(f"\n=== {company} ({len(jobs)} job mới) ===")
        for j in jobs:
            dept = f" | {j['department']}" if j.get("department") else ""
            loc = j.get("location") or "N/A"
            lines.append(f"- {j['title']}{dept}\n  📍 {loc}\n  {j['url']}")
    return "\n".join(lines)


def _build_html(grouped: dict) -> str:
    sections = []
    for company, jobs in grouped.items():
        rows = []
        for j in jobs:
            dept_html = (
                f"<div style='color:#666;font-size:13px;margin-top:2px;'>{j['department']}</div>"
                if j.get("department") else ""
            )
            loc = j.get("location") or "N/A"
            rows.append(f"""
            <tr>
              <td style="padding:12px 0;border-bottom:1px solid #eee;">
                <a href="{j['url']}" style="font-weight:600;font-size:15px;color:#1a73e8;text-decoration:none;">{j['title']}</a>
                {dept_html}
                <div style="color:#333;font-size:13px;margin-top:2px;">📍 {loc}</div>
              </td>
            </tr>""")

        sections.append(f"""
        <h3 style="margin:24px 0 4px;font-size:17px;">{company}
          <span style="color:#888;font-weight:normal;font-size:14px;">({len(jobs)} job mới)</span>
        </h3>
        <table style="width:100%;border-collapse:collapse;">{''.join(rows)}</table>""")

    return f"""
    <html><body style="font-family:Arial,Helvetica,sans-serif;color:#111;max-width:640px;margin:0 auto;padding:16px;">
      <h2 style="margin-bottom:4px;">🔔 Job mới phù hợp</h2>
      {''.join(sections)}
    </body></html>"""


def send_email(new_jobs: list[dict]):
    if not new_jobs:
        return

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["EMAIL_USER"]        # GitHub Secret
    password = os.environ["EMAIL_PASS"]    # GitHub Secret (App Password, không phải mật khẩu thường)
    to_addr = os.environ.get("EMAIL_TO", user)

    grouped = _group_by_company(new_jobs)

    msg = MIMEMultipart("alternative")
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = f"🔔 {len(new_jobs)} job mới ở {len(grouped)} công ty"
    msg.attach(MIMEText(_build_plain_text(grouped), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(grouped), "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())

    print(f"Đã gửi email báo {len(new_jobs)} job mới ({len(grouped)} công ty) tới {to_addr}")
