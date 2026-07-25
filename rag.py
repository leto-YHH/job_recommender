"""RAG 模組:職缺向量化 → 檢索 → Claude 重排序並產生推薦理由"""
import anthropic
import chromadb
from sentence_transformers import SentenceTransformer

import config
from jsonutil import parse_claude_json

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# 用來從自由文字的地點偏好裡抓出明確提到的縣市。類別二嚴格鎖定在這些
# 縣市,不做「鄰近縣市」的放寬。
TAIWAN_CITIES = [
    "台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
    "高雄市", "屏東縣", "台東縣", "花蓮縣", "宜蘭縣", "澎湖縣", "金門縣", "連江縣",
]


def _mentioned_locations(location_pref: str) -> list[str]:
    """從自由文字的地點偏好抓出明確提到的縣市"""
    return [city for city in TAIWAN_CITIES if city in location_pref]


_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        print(f"… 載入 embedding 模型 {config.EMBEDDING_MODEL}(首次會下載,較久)…")
        _embedder = SentenceTransformer(config.EMBEDDING_MODEL)
    return _embedder


def _job_text(j: dict) -> str:
    return (
        f"職稱:{j['title']}\n公司:{j['company']}\n地點:{j['location']}\n"
        f"薪資:{j['salary']}\n描述:{j['description']}"
    )


def retrieve(profile: dict, jobs: list[dict]) -> list[dict]:
    """把職缺建進向量庫,用求職者摘要檢索 top-k"""
    if not jobs:
        return []

    embedder = _get_embedder()
    chroma = chromadb.Client()                       # in-memory,每次執行重建
    coll = chroma.get_or_create_collection("jobs")

    texts = [_job_text(j) for j in jobs]
    print(f"… 對 {len(jobs)} 筆職缺做 embedding …")
    embeddings = embedder.encode(texts, show_progress_bar=False,
                                 normalize_embeddings=True)
    coll.add(
        ids=[j["job_id"] for j in jobs],
        embeddings=embeddings.tolist(),
        documents=texts,
    )

    query_vec = embedder.encode([profile["summary"]],
                                normalize_embeddings=True)
    k = min(config.RETRIEVE_TOP_K, len(jobs))
    result = coll.query(query_embeddings=query_vec.tolist(), n_results=k)

    hit_ids = set(result["ids"][0])
    by_id = {j["job_id"]: j for j in jobs}
    # 按檢索順序回傳
    return [by_id[i] for i in result["ids"][0] if i in hit_ids]


def retrieve_for_preferred_location(profile: dict, all_jobs: list[dict]) -> list[dict]:
    """類別二專用的候選池:直接從「全部去重後職缺」(不是 retrieve() 已經砍到
    top-K 的結果)篩出地點符合偏好的職缺,再單獨對這個子集合做語意排序。

    背景:retrieve() 是對全部職缺做一次通用的語意檢索,排序完全不看地點。
    如果使用者偏好的城市本來职缺供給量就少(例如非六都熱門地區),符合地點的
    職缺可能連 top-K(預設 50)都排不進去,類別二在檢索這關就已經沒東西可選,
    跟「重排序時濾掉不符地點」是兩回事。這裡另外開一條路徑,保證只要「全部
    職缺」裡有符合地點的,就一定會進到候選池,不會被其他地區的職缺排擠掉。
    """
    location_pref = profile.get("location_preference") or "不限"
    mentioned = _mentioned_locations(location_pref)
    if not mentioned:
        return []

    location_jobs = [j for j in all_jobs if any(city in (j.get("location") or "") for city in mentioned)]
    if not location_jobs:
        return []

    print(f"… 地點偏好({'/'.join(mentioned)})候選池:全部職缺中有 {len(location_jobs)} 筆符合,獨立做語意排序 …")
    return retrieve(profile, location_jobs)


GENERAL_RERANK_PROMPT = """你是一位嚴謹的職涯顧問。以下是求職者檔案與候選職缺,請挑出「條件與機會最好」的 \
{n} 筆,**先不考慮地點與遠距偏好**,任何城市的職缺都可以入選。

【求職者檔案】
摘要:{summary}
硬性條件(必須符合):{hard}

【候選職缺】
{jobs_block}

規則:
1. **違反硬性條件的職缺(薪資明顯低於要求、工作型態不符等,但先不管地點)一律排除,\
沒有例外**,即使因此湊不滿 {n} 筆也一樣,絕對不能為了湊數而放入違反硬性條件的職缺
2. 其餘依「技能匹配度」「錄取機會(職缺要求的年資/條件跟求職者背景越接近,機會越高)」\
「待遇吸引力」綜合排序,由好到差
3. 若合適的不足 {n} 筆,回傳實際合適的數量即可,寧缺勿濫,數量不足也不能放入不合格的職缺

只回傳 JSON 陣列,不要任何其他文字或 markdown 標記:
[
  {{"job_id": "...", "score": 1-10, "reason": "50字以內,說明錄取機會與待遇為何好"}}
]"""

PREFERRED_RERANK_PROMPT = """你是一位嚴謹的職涯顧問。以下是求職者檔案與候選職缺,請挑出最符合求職者\
「地點與工作方式偏好」、同時仍符合硬性條件的 {n} 筆。

【求職者檔案】
摘要:{summary}
硬性條件(必須符合):{hard}
地點偏好(嚴格鎖定,只能是這裡列出的縣市,不能放寬到其他縣市,即使覺得很近也不行):{location}
遠距/彈性偏好:{remote}
其他偏好:{prefs}

【候選職缺】
{jobs_block}

規則:
1. **違反硬性條件的職缺一律排除,沒有例外**,即使因此湊不滿 {n} 筆也一樣
2. **職缺地點必須是「地點偏好」列出的縣市之一,不是的話一律不能放入結果**,\
不能自己判斷其他縣市算不算鄰近、算不算可以接受
3. 在符合以上兩點的職缺中,優先選有遠距或彈性上班空間的職缺;\
其餘依技能匹配度與其他偏好符合度排序
4. 若真的湊不到 {n} 筆,回傳實際合適的數量即可,寧缺勿濫,\
絕對不能為了湊數放寬地點或硬性條件

只回傳 JSON 陣列,不要任何其他文字或 markdown 標記:
[
  {{"job_id": "...", "score": 1-10, "reason": "50字以內,說明為何符合偏好"}}
]"""

GAP_SUMMARY_PROMPT = """你是一位職涯顧問。以下是求職者檔案,以及這次爬到、跟他最相關的\
{n_jobs} 筆職缺(節錄職稱與描述,前面的編號之後要用來標註建議的依據):

【求職者檔案】
摘要:{summary}
硬性條件:{hard}
其他偏好:{prefs}

【相關職缺節錄,共 {n_jobs} 筆】
{jobs_block}

請分析這 {n_jobs} 筆職缺常見要求的技能、工具、證照,對照求職者目前具備的背景,\
按照求職者的職涯方向分領域(求職者背景可能橫跨多個領域,例如金融與\
AI/資料科學,就分成「金融領域」「AI/資料科學領域」等;若只有單一方向\
就只列一個領域),每個領域列出 2-4 項補強建議。

規則(非常重要):
1. 每項建議**必須包含具體名稱**(工具/框架/技術名稱、證照名稱、或可執行的專案方向),\
不能寫「加強程式能力」「提升溝通能力」「增進相關經驗」這類沒有具體名詞、\
無法直接照著做的空泛建議
2. 每項建議必須是**根據上面職缺清單實際歸納出來的**,不是憑一般常識講的通用建議;\
`evidence` 欄位填入這項建議依據的職缺編號(上面清單的編號,1 到 {n_jobs}),\
沒有具體依據的建議不要放進來
3. 同一項建議如果被多筆職缺提到,`evidence` 全部列出來,讓使用者知道這個缺口\
在目前職缺市場裡有多常見

只回傳 JSON,不要任何其他文字或 markdown 標記,格式:
{{
  "domains": [
    {{"name": "領域名稱", "suggestions": [
      {{"text": "具體建議(含工具/證照/專案方向名稱)", "evidence": [1, 5, 12]}}
    ]}}
  ]
}}"""


# Claude 偶爾會為了湊到 n 筆,把自己都認定違反硬性條件的職缺塞進結果、
# 並在 reason 裡寫出「應排除」之類的字。prompt 已經明講不能這樣做,但不
# 保證每次都遵守,這裡做一層程式碼保險,理由自相矛盾就直接濾掉。
_SELF_EXCLUDE_MARKERS = (
    "應排除", "應該排除", "應剔除", "不符合硬性條件",
    "未達硬性條件", "違反硬性條件", "不符硬性條件",
)


def _run_rerank(prompt: str, candidates: list[dict], n: int, category: str) -> list[dict]:
    ranked = None
    last_error = None
    for attempt in range(2):                          # 失敗重試一次,避免偶發空回應/解析失敗就整個崩潰
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            ranked = parse_claude_json(resp.content[0].text)
            break
        except Exception as e:
            last_error = e
            print(f"  [rerank] Claude 回應解析失敗,{'重試中' if attempt == 0 else '放棄'} …({e})")
    if ranked is None:
        print(f"  [rerank] 類別「{category}」重排序失敗,本次跳過這一類:{last_error}")
        return []

    by_id = {j["job_id"]: j for j in candidates}
    results = []
    for r in ranked:
        job = by_id.get(r.get("job_id"))
        if not job:
            continue
        reason = r.get("reason", "")
        if any(marker in reason for marker in _SELF_EXCLUDE_MARKERS):
            print(f"  [rerank] 濾掉自相矛盾的推薦 {job['job_id']}:{reason}")
            continue
        job = dict(job)
        job["score"] = r.get("score")
        job["reason"] = reason
        job["category"] = category
        results.append(job)
    return results[:n]


def rerank_general(profile: dict, candidates: list[dict], n: int | None = None) -> list[dict]:
    """類別一:不考慮地點/遠距偏好,只看硬性條件、技能契合度、錄取機會、待遇"""
    n = n or config.FINAL_RECOMMEND_N_GENERAL
    if not candidates:
        return []

    jobs_block = "\n\n".join(f"[{j['job_id']}]\n{_job_text(j)}" for j in candidates)
    prompt = GENERAL_RERANK_PROMPT.format(
        n=n,
        summary=profile["summary"],
        hard="、".join(profile.get("hard_requirements", [])) or "無",
        jobs_block=jobs_block,
    )
    print("… Claude 正在挑選類別一(條件與機會最佳,不限地點)…")
    return _run_rerank(prompt, candidates, n, "general")


def rerank_preferred(profile: dict, candidates: list[dict], n: int | None = None,
                      exclude_ids: set[str] | None = None) -> list[dict]:
    """類別二:符合硬性條件的前提下,優先考慮地點/遠距/其他偏好"""
    n = n or config.FINAL_RECOMMEND_N_PREFERRED
    exclude_ids = exclude_ids or set()
    pool = [j for j in candidates if j["job_id"] not in exclude_ids]
    if not pool:
        return []

    location_pref = profile.get("location_preference") or "不限"
    mentioned = _mentioned_locations(location_pref)

    jobs_block = "\n\n".join(f"[{j['job_id']}]\n{_job_text(j)}" for j in pool)
    prompt = PREFERRED_RERANK_PROMPT.format(
        n=n,
        summary=profile["summary"],
        hard="、".join(profile.get("hard_requirements", [])) or "無",
        location=location_pref,
        remote=profile.get("remote_preference") or "不限",
        prefs="、".join(profile.get("preferences", [])) or "無",
        jobs_block=jobs_block,
    )
    print("… Claude 正在挑選類別二(嚴格鎖定你的地點偏好)…")
    results = _run_rerank(prompt, pool, n, "preferred")

    # 地點保險:嚴格鎖定,不做鄰近縣市的放寬。只要抓得出明確地點偏好,
    # 結果的地點就必須包含其中之一(地點空白的無法判斷,放行)
    if mentioned:
        filtered = []
        for job in results:
            loc = job.get("location", "")
            if not loc or any(city in loc for city in mentioned):
                filtered.append(job)
            else:
                print(f"  [rerank] 濾掉不符地點偏好的推薦 {job['job_id']}:{loc}")
        results = filtered

    return results


def generate_gap_summary(profile: dict, candidates: list[dict]) -> dict:
    """分析這次爬到、跟求職者最相關的職缺,產生按領域分類的能力缺口建議"""
    empty = {"domains": []}
    if not candidates:
        return empty

    sample = candidates[:config.GAP_SUMMARY_SAMPLE_SIZE]
    jobs_block = "\n".join(
        f"{i}. {j['title']}:{j['description'][:400]}"
        for i, j in enumerate(sample, 1)
    )
    prompt = GAP_SUMMARY_PROMPT.format(
        n_jobs=len(sample),
        summary=profile["summary"],
        hard="、".join(profile.get("hard_requirements", [])) or "無",
        prefs="、".join(profile.get("preferences", [])) or "無",
        jobs_block=jobs_block,
    )

    print(f"… Claude 正在分析今天 {len(sample)} 筆相關職缺的能力缺口 …")
    try:
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_claude_json(resp.content[0].text)
    except Exception as e:
        print(f"  [rag] 能力缺口摘要產生失敗,略過:{e}")
        return empty


def format_gap_summary(gap: dict) -> str:
    """把按領域分類的能力缺口建議格式化成適合顯示/推播的文字"""
    domains = gap.get("domains") or []
    if not domains:
        return ""

    lines = []
    for d in domains:
        name = d.get("name", "")
        lines.append(f"對於{name},可以加強:")
        for i, s in enumerate(d.get("suggestions", []), 1):
            if isinstance(s, dict):
                text = s.get("text", "")
                evidence = s.get("evidence") or []
                tag = f"(依據 {len(evidence)} 筆相關職缺)" if evidence else ""
                lines.append(f"  {i}. {text}{tag}")
            else:
                lines.append(f"  {i}. {s}")
        lines.append("")
    return "\n".join(lines).strip()
