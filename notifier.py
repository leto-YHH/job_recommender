"""Telegram 推播模組

設定步驟:
  1. 跟 BotFather(https://t.me/BotFather)申請 Bot,取得 token
  2. 設定環境變數 TELEGRAM_BOT_TOKEN
  3. 傳一則任意訊息給你的 Bot
  4. 單獨執行 `python notifier.py`,會列出偵測到的 chat_id
  5. 設定環境變數 TELEGRAM_CHAT_ID,之後 main.py 執行完會自動推播
"""
import requests

import company_review
import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"
MESSAGE_LIMIT = 3500  # Telegram 單則訊息上限 4096 字,留一點餘裕


def _split_message(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """把過長的文字依行切成多則,不硬切斷單行內容"""
    lines = text.split("\n")
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_message(text: str) -> bool:
    """推播一段文字(過長會自動分段),回傳是否全部成功"""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("(尚未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID,略過 Telegram 推播)")
        return False

    url = API_BASE.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage")
    ok = True
    for chunk in _split_message(text):
        try:
            resp = requests.post(
                url,
                data={"chat_id": config.TELEGRAM_CHAT_ID, "text": chunk},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"Telegram 推播失敗:{e}")
            ok = False
    return ok


def _format_job_section(title: str, jobs: list[dict]) -> str:
    lines = [f"{title}(共 {len(jobs)} 筆)", ""]
    for i, j in enumerate(jobs, 1):
        lines.append(f"{i}. {j['title']}({j['platform']})")
        if j.get("company"):
            lines.append(f"   公司:{j['company']}")
        if j.get("location"):
            lines.append(f"   地點:{j['location']}")
        if j.get("salary"):
            lines.append(f"   薪資:{j['salary']}")
        lines.append(f"   匹配度:{j.get('score', '-')}/10")
        lines.append(f"   推薦理由:{j.get('reason', '')}")
        lines.append(f"   連結:{j['url']}")
        if j.get("company"):
            links = company_review.review_links(j["company"])
            lines.append(f"   公司評價參考:{links['interview_tw']} | {links['salary_tw']}")
        lines.append("")
    return "\n".join(lines).strip()


def format_report(gap_summary: str, general: list[dict], preferred: list[dict]) -> str:
    """把兩類別推薦結果 + 能力缺口總摘要格式化成適合傳送的文字(摘要放最後)"""
    sections = [
        _format_job_section("類別一:條件與機會最佳(不限地點)", general),
        _format_job_section("類別二:符合你的地點/遠距偏好", preferred),
    ]
    if gap_summary:
        sections.append(f"今日職缺能力缺口總摘要\n\n{gap_summary}")
    return "\n\n".join(sections).strip()


def send_report(gap_summary: str, general: list[dict], preferred: list[dict]) -> bool:
    """推播本次的能力缺口摘要與兩類別推薦結果"""
    return send_message(format_report(gap_summary, general, preferred))


def _detect_chat_id() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        print("請先設定環境變數 TELEGRAM_BOT_TOKEN")
        return

    url = API_BASE.format(token=config.TELEGRAM_BOT_TOKEN, method="getUpdates")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    chat_ids = set()
    for update in data.get("result", []):
        msg = update.get("message") or update.get("channel_post")
        if msg and "chat" in msg:
            chat_ids.add(msg["chat"]["id"])

    if not chat_ids:
        print("目前偵測不到 chat_id。請先傳一則訊息給你的 Bot,再重新執行本檔案。")
        return

    print("偵測到以下 chat_id:")
    for cid in chat_ids:
        print(f"  {cid}")
    example = next(iter(chat_ids))
    print(f'\n設定方式:$env:TELEGRAM_CHAT_ID = "{example}"')


if __name__ == "__main__":
    _detect_chat_id()
