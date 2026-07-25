"""推薦歷史紀錄:確保下次不再推薦相同職缺"""
import sqlite3
from datetime import datetime

import config


def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommended_jobs (
            job_id         TEXT PRIMARY KEY,   -- 例如 "104_8abc123" / "1111_123456"
            platform       TEXT NOT NULL,
            title          TEXT,
            company        TEXT,
            url            TEXT,
            recommended_at TEXT
        )
        """
    )
    return conn


def get_recommended_ids() -> set[str]:
    """取得所有已推薦過的 job_id"""
    with _conn() as conn:
        rows = conn.execute("SELECT job_id FROM recommended_jobs").fetchall()
    return {r[0] for r in rows}


def get_recommended_signatures() -> set[str]:
    """第二層去重:公司+職稱 的簽名,擋掉重新刊登換 ID 的職缺"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT company, title FROM recommended_jobs"
        ).fetchall()
    return {f"{(c or '').strip()}::{(t or '').strip()}" for c, t in rows}


def filter_new_jobs(jobs: list[dict]) -> list[dict]:
    """剔除已推薦過的職缺(ID 精準比對 + 公司職稱簽名比對)"""
    seen_ids = get_recommended_ids()
    seen_sigs = get_recommended_signatures()
    fresh = []
    for j in jobs:
        sig = f"{j.get('company', '').strip()}::{j.get('title', '').strip()}"
        if j["job_id"] in seen_ids or sig in seen_sigs:
            continue
        fresh.append(j)
    return fresh


def save_recommendations(jobs: list[dict]) -> None:
    """把本次推薦的職缺寫入歷史"""
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO recommended_jobs
                (job_id, platform, title, company, url, recommended_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (j["job_id"], j["platform"], j.get("title"), j.get("company"),
                 j.get("url"), now)
                for j in jobs
            ],
        )
