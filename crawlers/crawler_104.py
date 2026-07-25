"""104 人力銀行爬蟲

104 的搜尋頁背後有一個回傳 JSON 的端點,直接打它比解析 HTML 穩定得多。
注意:這是非官方端點,格式可能隨時變動;若失效請打開瀏覽器開發者工具
(Network 分頁)搜尋職缺,找到名稱類似 /jobs/search/api/jobs 的請求,
比對參數與回傳格式後修改本檔。

2026/7 更新:舊的 /jobs/search/list 端點已經 404,改用側錄到的
/jobs/search/api/jobs;回應結構也從 {"data": {"list": [...]}} 變成
{"data": [...]},薪資也從 salaryDesc 字串改成 salaryLow/salaryHigh 數字。
"""
import random
import time

import requests

import config

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Accept": "application/json",
}


def _format_salary(low, high) -> str:
    low, high = low or 0, high or 0
    if not low and not high:
        return "面議"
    if high >= 9_000_000:
        return f"{low:,}元以上"
    if low == high:
        return f"{low:,}元"
    return f"{low:,}~{high:,}元"


def search(keyword: str, max_pages: int | None = None) -> list[dict]:
    """依關鍵字搜尋職缺,回傳統一格式的職缺 list"""
    max_pages = max_pages or config.MAX_PAGES_PER_KEYWORD
    jobs: list[dict] = []

    for page in range(1, max_pages + 1):
        params = {
            "ro": 0,            # 0=全部, 1=全職
            "keyword": keyword,
            "order": 15,        # 15=符合度排序
            "asc": 0,
            "page": page,
            "pagesize": 20,
            "mode": "s",
            "jobsource": "index_s",
        }
        try:
            resp = requests.get(SEARCH_URL, params=params,
                                headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [104] 第 {page} 頁抓取失敗:{e}")
            break

        items = data.get("data") or []
        if not items:
            break

        for it in items:
            job_no = str(it.get("jobNo") or "")
            link = it.get("link", {}).get("job", "")
            if link.startswith("//"):
                link = "https:" + link
            jobs.append({
                "job_id": f"104_{job_no}",
                "platform": "104",
                "title": it.get("jobName", ""),
                "company": it.get("custName", ""),
                "location": it.get("jobAddrNoDesc", ""),
                "salary": _format_salary(it.get("salaryLow"), it.get("salaryHigh")),
                "description": it.get("description", ""),
                "url": link,
            })

        print(f"  [104] 「{keyword}」第 {page} 頁:{len(items)} 筆")
        time.sleep(random.uniform(*config.CRAWL_DELAY_RANGE))

    return jobs
