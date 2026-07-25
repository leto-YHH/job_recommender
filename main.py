"""求職推薦系統主程式

流程:讀履歷(選填)→ 訪談 → 爬蟲(104+1111+JobFrog+CakeResume)→ 歷史去重 → RAG 檢索
      → 能力缺口摘要 → Claude 兩類別重排序 → 輸出推薦 → Telegram 推播 → 寫入歷史

推薦分兩類:
  類別一(不限地點):只看硬性條件、技能契合度、錄取機會、待遇,不考慮地點/遠距偏好
  類別二(符合偏好):在符合硬性條件的前提下,優先地點/遠距偏好符合的職缺

用法:
  python main.py                履歷用問答方式收集
  python main.py 履歷路徑.pdf    先讀履歷,只追問履歷沒寫到的資訊
"""
import sys

import company_review
import config
import github_profile
import history
import interview
import notifier
import rag
import resume
from crawlers import crawler_104, crawler_1111, crawler_cakeresume, crawler_jobfrog


def crawl_all(keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for kw in keywords:
        print(f"\n開始爬取關鍵字:「{kw}」")
        for j in crawler_104.search(kw) + crawler_1111.search(kw):
            if j["job_id"] not in seen:
                seen.add(j["job_id"])
                jobs.append(j)

    # jobfrog / cakeresume 都沒有伺服器端關鍵字搜尋,只抓一次(模組內快取)全站職缺
    print("\n開始爬取 JobFrog(外商科技職缺)")
    for j in crawler_jobfrog.search(keywords[0] if keywords else ""):
        if j["job_id"] not in seen:
            seen.add(j["job_id"])
            jobs.append(j)

    print("\n開始爬取 CakeResume")
    for j in crawler_cakeresume.search(keywords[0] if keywords else ""):
        if j["job_id"] not in seen:
            seen.add(j["job_id"])
            jobs.append(j)

    return jobs


def print_jobs(recommendations: list[dict]) -> None:
    for i, j in enumerate(recommendations, 1):
        print(f"\n{i}. {j['title']}({j['platform']})")
        if j.get("company"):
            print(f"   公司:{j['company']}")
        if j.get("location"):
            print(f"   地點:{j['location']}")
        if j.get("salary"):
            print(f"   薪資:{j['salary']}")
        print(f"   匹配度:{j.get('score', '-')}/10")
        print(f"   推薦理由:{j.get('reason', '')}")
        print(f"   連結:{j['url']}")
        if j.get("company"):
            links = company_review.review_links(j["company"])
            print(f"   公司評價參考:{links['interview_tw']} | {links['salary_tw']}")


def main() -> None:
    if not config.ANTHROPIC_API_KEY:
        sys.exit("請先設定環境變數 ANTHROPIC_API_KEY")

    # 0. 讀履歷(選填,argv[1] 傳入路徑)
    resume_text = None
    if len(sys.argv) > 1:
        try:
            resume_text = resume.read_resume(sys.argv[1])
            print(f"已讀取履歷:{sys.argv[1]}({len(resume_text)} 字)")
        except Exception as e:
            sys.exit(f"履歷讀取失敗:{e}")

    # 0b. 選填:接上 GitHub 公開專案摘要,當履歷內容的補充
    if config.GITHUB_USERNAME:
        github_text = github_profile.fetch_profile(config.GITHUB_USERNAME)
        if github_text:
            resume_text = f"{resume_text}\n\n{github_text}" if resume_text else github_text

    # 1. 訪談
    profile = interview.run_interview(resume_text)

    # 2. 爬蟲
    jobs = crawl_all(profile["search_keywords"])
    print(f"\n共爬到 {len(jobs)} 筆職缺")
    if not jobs:
        sys.exit("沒有爬到任何職缺,請檢查網路或爬蟲是否需要更新")

    # 3. 歷史去重
    fresh = history.filter_new_jobs(jobs)
    skipped = len(jobs) - len(fresh)
    if skipped:
        print(f"已排除 {skipped} 筆先前推薦過的職缺")
    if not fresh:
        sys.exit("所有職缺都推薦過了,試著更換關鍵字或增加爬取頁數")

    # 4. RAG 檢索
    candidates = rag.retrieve(profile, fresh)

    # 4b. 類別二專用:地點偏好獨立檢索,避免供給量小的地區被通用 top-K 排擠掉
    location_candidates = rag.retrieve_for_preferred_location(profile, fresh)

    # 5. 能力缺口摘要(按領域分類,放在最後輸出;用通用候選池,反映整體市場)
    gap_data = rag.generate_gap_summary(profile, candidates)
    gap_text = rag.format_gap_summary(gap_data)

    # 6. Claude 兩類別重排序
    general = rag.rerank_general(profile, candidates)

    seen_ids = {j["job_id"] for j in candidates}
    preferred_pool = candidates + [j for j in location_candidates if j["job_id"] not in seen_ids]
    preferred = rag.rerank_preferred(
        profile, preferred_pool, exclude_ids={j["job_id"] for j in general}
    )
    recommendations = general + preferred
    if not recommendations:
        sys.exit("沒有符合條件的職缺,可放寬條件後重新執行")

    # 7. 輸出
    print("\n" + "=" * 50)
    print(f"類別一:條件與機會最佳(不限地點)共 {len(general)} 筆")
    print("=" * 50)
    print_jobs(general)

    print("\n" + "=" * 50)
    print(f"類別二:符合你的地點/遠距偏好 共 {len(preferred)} 筆")
    print("=" * 50)
    print_jobs(preferred)

    if gap_text:
        print("\n" + "=" * 50)
        print("今日職缺能力缺口總摘要")
        print("=" * 50)
        print(gap_text)

    # 8. Telegram 推播
    if notifier.send_report(gap_text, general, preferred):
        print("\n已推播到 Telegram")

    # 9. 寫入歷史,下次不再推薦
    history.save_recommendations(recommendations)
    print(f"\n已記錄本次推薦,下次執行會自動排除這 {len(recommendations)} 筆。")


if __name__ == "__main__":
    main()
