"""公司評價參考連結(interview.tw 面試心得 / salary.tw 薪水評價)

這兩個網站的公司搜尋功能(/search?q=...)在 robots.txt 明確寫
Disallow: /search?*,不能自動爬取內容;而公司頁面網址是隨機 ID
(例如 /c/Dok7),沒有辦法從公司名稱直接猜到網址,也没有反查的
公開名單可以離線建索引,所以這裡不爬取實際評價內容。

改成組出「搜尋這間公司」的連結,附加在推薦結果旁邊給使用者自己
點進去看 —— 不對這兩個網站發送任何自動化請求,純粹是產生連結,
權重是 0,不影響任何篩選或排序。
"""
from urllib.parse import quote


def review_links(company: str) -> dict:
    """回傳這間公司在 interview.tw / salary.tw 的搜尋連結(給人工參考用)"""
    if not company:
        return {}
    q = quote(company)
    return {
        "interview_tw": f"https://interview.tw/search?q={q}",
        "salary_tw": f"https://salary.tw/search?q={q}",
    }
