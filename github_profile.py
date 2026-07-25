"""GitHub 公開專案摘要

透過 GitHub 官方公開 REST API(https://api.github.com,不需要 token 也能查
公開資料,未認證請求有每小時 60 次的速率限制,這裡的呼叫量遠低於此)抓取
使用者公開 repo 的名稱、語言、README 摘要,整理成一段文字接在履歷後面,
當作履歷內容的補充,讓訪談/彙整檔案/能力缺口分析都能參考到實際做過的專案
(不是只看履歷文字怎麼寫)。

只抓公開資訊、不需要登入、不對任何反爬機制做處理 —— 這是 GitHub 官方提供
給這種用途的介面,跟爬 104/1111/JobFrog/CakeResume 職缺網站是完全不同的情境。

過濾掉 fork 出來的 repo(不是使用者自己寫的),依最近 push 時間排序,取前
config.GITHUB_MAX_REPOS 個。
"""
import base64

import requests

import config

API_BASE = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": config.USER_AGENT,
}
README_SNIPPET_LEN = 600


def _fetch_readme(owner: str, repo: str) -> str:
    try:
        resp = requests.get(f"{API_BASE}/repos/{owner}/{repo}/readme",
                             headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return ""
        content_b64 = resp.json().get("content", "")
        text = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
        return text.strip()[:README_SNIPPET_LEN]
    except Exception:
        return ""


def fetch_profile(username: str) -> str:
    """回傳可以直接接在履歷文字後面的 GitHub 專案摘要文字,失敗回傳空字串"""
    if not username:
        return ""

    try:
        resp = requests.get(f"{API_BASE}/users/{username}/repos",
                             headers=HEADERS, timeout=10,
                             params={"sort": "pushed", "per_page": 30})
        resp.raise_for_status()
        repos = resp.json()
    except Exception as e:
        print(f"  [github] 讀取 {username} 的 repo 列表失敗,略過:{e}")
        return ""

    repos = [r for r in repos if not r.get("fork")][:config.GITHUB_MAX_REPOS]
    if not repos:
        print(f"  [github] {username} 沒有公開的非 fork repo,略過")
        return ""

    print(f"  [github] 讀取 {username} 的 {len(repos)} 個公開 repo …")
    sections = [f"GitHub 專案(來自 github.com/{username},依最近更新排序):"]
    for r in repos:
        name = r["name"]
        language = r.get("language") or "未標示語言"
        description = r.get("description") or ""
        readme = _fetch_readme(username, name)
        block = f"- {name}({language}){'：' + description if description else ''}"
        if readme:
            block += f"\n  README 摘要:{readme}"
        sections.append(block)

    return "\n".join(sections)
