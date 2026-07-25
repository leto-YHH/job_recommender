"""1111 人力銀行爬蟲

2026/7 更新:1111 的搜尋結果頁現在完全由 JS 動態渲染,而且會先跑一個
反爬驗證(altcha),單純 requests 抓到的只是空殼 HTML(<title>Loading...
</title>,沒有任何 /job/ 連結)。改用 Playwright 開無頭瀏覽器把頁面
渲染出來後再解析,選擇器邏輯不變(仍是以 /job/<id> 連結為錨點的
防禦性寫法),等 JS 執行完的 HTML 結構跟以前差不多。

若頁面改版導致選不到職缺,請打開瀏覽器開發者工具比對新結構,更新
_parse_page() 即可,不需要更動 Playwright 呼叫邏輯。
company/location 欄位卡片結構變動大,目前仍留空,description 用整張
卡片文字代替。
"""
import random
import re
import time
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

import config

SEARCH_URL = "https://www.1111.com.tw/search/job"


def _extract_job_id(url: str) -> str:
    """從職缺 URL 取出編號,例如 /job/123456/ -> 123456"""
    m = re.search(r"/job/(\d+)", url)
    return m.group(1) if m else url


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # 1111 的職缺卡片:以連到 /job/<數字> 的連結為錨點,往上找卡片容器
    seen_links = set()
    for a in soup.select('a[href*="/job/"]'):
        href = a.get("href", "")
        if not re.search(r"/job/\d+", href):
            continue
        if href.startswith("/"):
            href = "https://www.1111.com.tw" + href
        href = href.split("?")[0]
        if href in seen_links:
            continue
        seen_links.add(href)

        card = a
        for _ in range(4):                      # 往上最多找 4 層當卡片
            if card.parent is None:
                break
            card = card.parent
        text = card.get_text(" ", strip=True)

        title = a.get_text(strip=True)
        if not title or len(title) < 2:
            continue

        jobs.append({
            "job_id": f"1111_{_extract_job_id(href)}",
            "platform": "1111",
            "title": title,
            "company": "",                       # 卡片結構變動大,先留空
            "location": "",
            "salary": "",
            "description": text[:500],           # 用整張卡片文字當摘要
            "url": href,
        })
    return jobs


def search(keyword: str, max_pages: int | None = None) -> list[dict]:
    """依關鍵字搜尋職缺,回傳統一格式的職缺 list

    用 Playwright 渲染搜尋結果頁(見模組說明);同一次呼叫共用一個
    瀏覽器分頁,逐頁導頁解析,結束後關閉瀏覽器。
    """
    max_pages = max_pages or config.MAX_PAGES_PER_KEYWORD
    jobs: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=config.USER_AGENT)

        for pg in range(1, max_pages + 1):
            url = f"{SEARCH_URL}?ks={quote(keyword)}&page={pg}"
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)
                html = page.content()
            except Exception as e:
                print(f"  [1111] 第 {pg} 頁抓取失敗:{e}")
                break

            page_jobs = _parse_page(html)
            if not page_jobs:
                print(f"  [1111] 第 {pg} 頁解析不到職缺(可能改版或已無更多結果)")
                break

            jobs.extend(page_jobs)
            print(f"  [1111] 「{keyword}」第 {pg} 頁:{len(page_jobs)} 筆")
            time.sleep(random.uniform(*config.CRAWL_DELAY_RANGE))

        browser.close()

    return jobs
