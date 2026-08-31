import os
import sqlite3
import glob
from datetime import datetime, timezone, timedelta
from src.notifier import send_discord_notification
from dotenv import load_dotenv

def generate_daily_summary():
    load_dotenv()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db_files = glob.glob("data/*.db")
    if not db_files:
        print("No database files found.")
        return

    summary_lines = []
    total_uploads = 0

    for db_path in db_files:
        channel_name = os.path.basename(db_path).replace(".db", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*) as count FROM runs 
            WHERE run_date IN (?, ?) AND status = 'success'
        """, (yesterday, today))
        uploads = c.fetchone()["count"]
        total_uploads += uploads

        c.execute("""
            SELECT status, COUNT(*) as count FROM runs 
            WHERE run_date = ? 
            GROUP BY status
        """, (today,))
        runs_today = {row["status"]: row["count"] for row in c.fetchall()}

        summary_lines.append(f"• **{channel_name}**: {uploads} uploads | Today: {runs_today}")
        conn.close()

    content = "\n".join(summary_lines)
    send_discord_notification(
        webhook_url=webhook_url,
        title=f"📊 Daily Automation Summary ({today})",
        description=f"**Total Recent Uploads:** {total_uploads}\n\n{content}",
        status="info"
    )

if __name__ == "__main__":
    generate_daily_summary()
