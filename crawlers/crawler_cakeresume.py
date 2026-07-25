"""CakeResume(cake.me)爬蟲

cake.me 的 robots.txt 完全開放(沒有任何 Disallow),但搜尋列表頁
`/jobs/for-<profession>` 是純前端渲染,而且會先跑一次 Cloudflare
Managed Challenge(「Just a moment...」JS 驗證)才能看到內容 ——
這條路徑不碰,不對驗證機制做任何形式的繞過。

改走 `/companies/<slug>` 公司頁:這頁是伺服器端渲染,直接 requests
就拿得到 200 與完整 HTML,沒有任何驗證關卡。頁面裡有一段
`<script id="__NEXT_DATA__">` 內嵌 JSON,裡面就是 React/Next.js
渲染這頁用的原始資料(`props.pageProps.truncatedVisibleJobs.data`),
包含結構化欄位(職稱、地點、薪資、遠距、職缺敘述),比正規表示式
硬解 HTML 穩定精確得多。

公司清單來源:sitemap-companies.xml(.gz)。

已知限制:公司頁預設(伺服器端渲染出來)只有前 5 筆職缺,更多筆數
要點「Load more」用前端 JS 動態載入,目前沒找到對應的公開 API 端點,
所以每家公司只能拿到前 5 筆在架職缺 —— 跟 JobFrog 一樣,樣本有上限
但合法、不需要繞過任何驗證機制。

若改版導致解析不到東西:先用瀏覽器開發者工具檢查
`__NEXT_DATA__` 的 JSON 結構是否變了(key 名稱、巢狀路徑),
不要假設是程式碼本身的 bug —— 這是內部資料結構,改版機率比
公開 API 更高。
"""
import json
import random
import re
import time

import requests
from bs4 import BeautifulSoup

import config

BASE_URL = "https://www.cake.me"
SITEMAP_URL = f"{BASE_URL}/sitemap-companies.xml.gz"

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "zh-TW,zh;q=0.9",
}

_cache: list[dict] | None = None


def _get_company_slugs() -> list[str]:
    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [cakeresume] 讀取 sitemap 失敗:{e}")
        return []
    # sitemap 裡每家公司對應 3 條 <loc>:/companies/<slug>、/team、/jobs 子路徑,
    # 錨定 </loc> 結尾只取裸 slug 那條
    slugs = re.findall(r"/companies/([a-zA-Z0-9_-]+)</loc>", resp.text)
    return slugs[:config.CAKERESUME_MAX_COMPANIES]


def _format_salary(job: dict) -> str:
    if job.get("hide_salary_completely"):
        return "面議"
    try:
        low = float(job.get("salary_min") or 0)
        high = float(job.get("salary_max") or 0)
    except (TypeError, ValueError):
        return "面議"
    if not low and not high:
        return "面議"
    currency = job.get("salary_currency") or "TWD"
    if low == high:
        return f"{currency} {low:,.0f}"
    return f"{currency} {low:,.0f}~{high:,.0f}"


def _extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _parse_company_page(html: str, slug: str) -> list[dict]:
    data = _extract_next_data(html)
    if not data:
        return []

    props = data.get("props", {}).get("pageProps", {})
    company = props.get("company") or {}
    company_name = company.get("name") or slug

    job_page = props.get("truncatedVisibleJobs") or {}
    jobs = []
    for j in job_page.get("data", []):
        path = j.get("path")
        title = j.get("title")
        if not path or not title:
            continue

        locations = []
        for loc in j.get("locations") or []:
            name = loc.get("full_name") or loc.get("full_name_en")
            if name and name not in locations:
                locations.append(name)

        jobs.append({
            "job_id": f"cake_{path}",
            "platform": "cakeresume",
            "title": title,
            "company": company_name,
            "location": "、".join(locations),
            "salary": _format_salary(j),
            "description": (j.get("processed_description") or "")[:500],
            "url": f"{BASE_URL}/companies/{slug}/jobs/{path}",
        })
    return jobs


def _fetch_all_jobs() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache

    slugs = _get_company_slugs()
    print(f"  [cakeresume] 共 {len(slugs)} 家公司,開始抓取職缺列表 …")

    jobs: list[dict] = []
    for slug in slugs:
        try:
            resp = requests.get(f"{BASE_URL}/companies/{slug}",
                                 headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [cakeresume] 公司頁 {slug} 抓取失敗:{e}")
            continue

        jobs.extend(_parse_company_page(resp.text, slug))
        time.sleep(random.uniform(*config.CRAWL_DELAY_RANGE))

    print(f"  [cakeresume] 共抓到 {len(jobs)} 筆職缺")
    _cache = jobs
    return jobs


def search(keyword: str) -> list[dict]:
    """回傳職缺列表(公司頁沒有伺服器端關鍵字搜尋,keyword 目前不用於過濾,
    相關性交給後續 RAG 語意檢索判斷,做法比照 crawler_jobfrog.py)"""
    return _fetch_all_jobs()
