"""JobFrog(職缺青蛙,job-frog.com)爬蟲

這是一個外商科技職缺聚合網站。首頁的搜尋/篩選結果完全由前端 JS
動態渲染,原始 HTML 是空的;而且該站 robots.txt 明確寫
`Disallow: /api/`,不能直接打它背後的 API。

但每間公司的 `/companies/<slug>` 頁面是伺服器端渲染的靜態 HTML,
列出該公司目前的職缺(標題、地點、職務類型、年資要求),而且
robots.txt 允許爬取,所以改用這個入口:
  1. 讀 sitemap.xml 取得所有公司 slug
  2. 逐一爬 /companies/<slug>,解析職缺卡片

JobFrog 沒有提供伺服器端關鍵字搜尋,而且職缺標題幾乎都是英文
(外商職缺),求職者的 search_keywords 多半是中文,直接做字串比對
意義不大。因此 search() 不用 keyword 過濾,而是回傳(有上限、
模組層級快取一次)的職缺列表,相關性交給後續的 RAG 語意檢索判斷。
"""
import random
import re
import time

import requests
from bs4 import BeautifulSoup

import config

BASE_URL = "https://www.job-frog.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

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
        print(f"  [jobfrog] 讀取 sitemap 失敗:{e}")
        return []
    slugs = re.findall(r"/companies/([a-zA-Z0-9-]+)</loc>", resp.text)
    return slugs[:config.JOBFROG_MAX_COMPANIES]


def _parse_company_page(html: str, company: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for a in soup.select('a[href^="/jobs/"]'):
        href = a.get("href", "")
        m = re.match(r"^/jobs/(\d+)$", href)
        if not m:
            continue
        spans = a.find_all("span")
        title = spans[0].get_text(strip=True) if spans else ""
        if not title:
            continue
        meta = spans[1].get_text(" ", strip=True) if len(spans) > 1 else ""
        location = meta.split("·")[0].strip() if meta else ""
        jobs.append({
            "job_id": f"jobfrog_{m.group(1)}",
            "platform": "jobfrog",
            "title": title,
            "company": company,
            "location": location,
            "salary": "",
            "description": meta,
            "url": f"{BASE_URL}{href}",
        })
    return jobs


def _fetch_all_jobs() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache

    slugs = _get_company_slugs()
    print(f"  [jobfrog] 共 {len(slugs)} 家公司,開始抓取職缺列表 …")

    jobs: list[dict] = []
    for slug in slugs:
        try:
            resp = requests.get(f"{BASE_URL}/companies/{slug}",
                                 headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [jobfrog] 公司頁 {slug} 抓取失敗:{e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        company_name = h1.get_text(strip=True) if h1 else slug
        jobs.extend(_parse_company_page(resp.text, company_name))

        time.sleep(random.uniform(*config.CRAWL_DELAY_RANGE))

    print(f"  [jobfrog] 共抓到 {len(jobs)} 筆職缺")
    _cache = jobs
    return jobs


def search(keyword: str) -> list[dict]:
    """回傳職缺列表(見模組說明,keyword 目前不用於過濾)"""
    return _fetch_all_jobs()
