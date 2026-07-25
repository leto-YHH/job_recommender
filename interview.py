"""問卷訪談模組:Claude 出題(選擇題 + 簡答題)→ 彙整成求職者檔案

問答紀錄會存到 config.PROFILE_STATE_PATH,下次執行時偵測到就不會重問
基本題/履歷分析,只會請 Claude 出「全新」的追問(避免重複),累積在
同一份 qa_log 上,讓求職者檔案跟著更新。
"""
import json
import re
from pathlib import Path

import anthropic

import config
from jsonutil import parse_claude_json

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# 固定的基本題,確保一定拿得到搜尋所需的核心資訊
BASE_QUESTIONS = [
    {
        "type": "choice",
        "question": "你想找的工作型態是?",
        "options": ["全職", "兼職", "實習", "接案/遠端"],
    },
    {
        "type": "text",
        "question": "你想找什麼類型的職位?(例如:後端工程師、行銷企劃、會計)",
    },
    {
        "type": "text",
        "question": "偏好的工作地點?(例如:台北市、桃園市、不限)",
    },
    {
        "type": "text",
        "question": "期望月薪範圍?(例如:40k-55k,可填「面議」)",
    },
    {
        "type": "text",
        "question": "你具備哪些技能或證照?(自由描述)",
    },
    {
        "type": "text",
        "question": "相關工作年資大約多久?(例如:新鮮人、2年、5年以上)",
    },
]

RESUME_QUESTIONS_PROMPT = """你是一位資深職涯顧問。以下是求職者的履歷全文:

{resume}

請判斷履歷中【已經寫清楚】與【還沒寫清楚或完全沒提到】的求職偏好資訊,\
只針對「還沒寫清楚」的項目出題(選擇題或簡答題),\
確保下列項目只要履歷沒寫清楚就一定要問到:工作型態(全職/兼職/實習/接案遠端)、\
目標職位、偏好工作地點、期望月薪範圍。履歷已經寫清楚的項目請不要重複詢問。

特別注意:如果履歷中的工作經歷跟目標職位方向明顯不同(例如過去做家教、\
餐飲服務、行政工作,但目標是資料科學/AI/金融等專業領域),不能把履歷上的\
總工作年資直接當作該目標領域的相關年資,這種情況務必追問求職者在目標領域\
的實際相關經驗大約等同於幾年(可能是應屆/新鮮人,也可能有相關專案/實習/\
自學成果可以計入)。

只回傳 JSON 陣列,不要任何其他文字或 markdown 標記,格式:
[
  {{"type": "choice", "question": "...", "options": ["...", "..."]}},
  {{"type": "text", "question": "..."}}
]"""

FOLLOWUP_PROMPT = """你是一位資深職涯顧問。以下是求職者目前的問答紀錄:

{qa_log}

請根據以上回答,設計 2-3 題「追問」,目的是讓職缺推薦更精準。
可以問偏好(公司規模、產業、加班接受度、通勤時間…)或釐清模糊的回答。
選擇題與簡答題混搭。

只回傳 JSON 陣列,不要任何其他文字或 markdown 標記,格式:
[
  {{"type": "choice", "question": "...", "options": ["...", "..."]}},
  {{"type": "text", "question": "..."}}
]"""

REFRESH_PROMPT = """你是一位資深職涯顧問。以下是求職者之前填寫過的完整問答紀錄(已經有答案了,\
不要重複問一樣或非常相似的問題):

{qa_log}

請設計 2-3 題「全新」的追問,幫助更新這次的求職偏好,可以參考的方向:
- 是否有新學到的技能、剛考到的證照、新的專案經驗
- 期望薪資、地點、遠距/彈性工作的偏好是否有調整
- 對先前推薦結果的回饋(太多/太少、方向對不對、有沒有已經應徵或錄取)
- 之前完全沒問過的偏好(公司規模、產業、加班接受度、通勤時間…)

選擇題與簡答題混搭,務必跟之前的問答紀錄不重複、不高度相似。

只回傳 JSON 陣列,不要任何其他文字或 markdown 標記,格式:
[
  {{"type": "choice", "question": "...", "options": ["...", "..."]}},
  {{"type": "text", "question": "..."}}
]"""

PROFILE_PROMPT = """以下是一位求職者的完整問答紀錄:

{qa_log}

請彙整成結構化的求職者檔案。只回傳 JSON,不要任何其他文字或 markdown 標記:
{{
  "summary": "一段 100 字以內的求職者描述(用於向量檢索,請包含職位方向、技能、\
與目標職位相關的經驗程度,不用包含地點)。年資務必寫『跟目標職位相關』的程度,\
不是總工作年資——如果過去的工作(例如家教、餐飲、行政)跟目標領域無關,\
即使做了幾年也要寫成應屆/新鮮人等級,不能讓不相關的年資誤導職缺媒合",
  "search_keywords": ["給人力銀行搜尋用的關鍵字,3-5 個,例如職稱或技能"],
  "hard_requirements": ["真正不能妥協的硬性條件,例如:月薪至少45k、需全職、週休二日。不要把工作地點放在這裡,地點是偏好不是硬性條件"],
  "location_preference": "偏好的工作地點,例如:高雄市;沒有特別偏好就填「不限」",
  "remote_preference": "遠距/彈性上班的偏好,例如:希望一週有2天可以遠距;沒有特別偏好就填「不限」",
  "preferences": ["其他軟性偏好,例如:偏好中小型公司、希望不加班"]
}}"""


def _ask_claude(prompt: str) -> str:
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _load_state() -> dict | None:
    """讀取上次訪談留下的問答紀錄與求職者檔案,沒有就回傳 None"""
    path = Path(config.PROFILE_STATE_PATH)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_state(qa_log: list[str], profile: dict) -> None:
    """把這次的問答紀錄與求職者檔案存起來,給下次執行避免重複發問"""
    path = Path(config.PROFILE_STATE_PATH)
    data = {"qa_log": qa_log, "profile": profile}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ask_user(q: dict) -> str:
    """在終端機呈現一題並取得回答"""
    print(f"\nQ: {q['question']}")
    if q["type"] == "choice":
        for i, opt in enumerate(q["options"], 1):
            print(f"   {i}. {opt}")
        while True:
            raw = input("請輸入選項編號(或直接輸入文字): ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(q["options"]):
                ans = q["options"][int(raw) - 1]
                print(f"  已記錄:{ans}")
                return ans
            # 容錯:打錯字但夾帶一個有效選項數字(例如「篇好2」想選第 2 項)
            m = re.fullmatch(r"\D*(\d+)\D*", raw)
            if m and 1 <= int(m.group(1)) <= len(q["options"]):
                ans = q["options"][int(m.group(1)) - 1]
                print(f"  已記錄:{ans}(從「{raw}」判斷你選了第 {m.group(1)} 項,如果不對請告訴我)")
                return ans
            if raw:
                return raw
    else:
        while True:
            raw = input("你的回答: ").strip()
            if raw:
                return raw


def run_interview(resume_text: str | None = None) -> dict:
    """執行完整訪談流程,回傳求職者檔案 dict

    若偵測到上次留下的問答紀錄(config.PROFILE_STATE_PATH),不會重問
    基本題/履歷分析,只請 Claude 出全新的追問;否則才走第一次的完整
    流程(有履歷就只問履歷沒寫清楚的,沒有就走固定基本問題)。
    """
    state = _load_state()
    qa_log: list[str] = list(state["qa_log"]) if state else []

    print("=" * 50)
    print("開始求職訪談(回答越具體,推薦越準確)")
    print("=" * 50)

    if state:
        print("\n偵測到上次填寫過的求職者檔案,這次只問新的/需要更新的問題 …")
        try:
            followups = parse_claude_json(
                _ask_claude(REFRESH_PROMPT.format(qa_log="\n\n".join(qa_log)))
            )
        except Exception as e:
            print(f"(產生更新問題失敗,略過:{e})")
            followups = []
        for q in followups:
            ans = _ask_user(q)
            qa_log.append(f"Q: {q['question']}\nA: {ans}")
    else:
        if resume_text:
            qa_log.append(f"履歷全文:\n{resume_text}")
            print("\n… 正在分析履歷,只會詢問履歷沒寫清楚的資訊 …")
            try:
                questions = parse_claude_json(
                    _ask_claude(RESUME_QUESTIONS_PROMPT.format(resume=resume_text))
                )
            except Exception as e:
                print(f"(履歷分析失敗,改問基本問題:{e})")
                questions = BASE_QUESTIONS
        else:
            questions = BASE_QUESTIONS

        # 第一輪:履歷缺漏的資訊(或無履歷時的固定基本題)
        for q in questions:
            ans = _ask_user(q)
            qa_log.append(f"Q: {q['question']}\nA: {ans}")

        # 第二輪:Claude 依回答動態追問
        print("\n… 正在根據你的回答產生追問 …")
        try:
            followups = parse_claude_json(
                _ask_claude(FOLLOWUP_PROMPT.format(qa_log="\n\n".join(qa_log)))
            )
            for q in followups:
                ans = _ask_user(q)
                qa_log.append(f"Q: {q['question']}\nA: {ans}")
        except Exception as e:
            print(f"(追問產生失敗,略過:{e})")

    # 彙整成檔案(用累積的完整問答紀錄,含之前執行留下的)
    print("\n… 正在彙整你的求職者檔案 …")
    profile = parse_claude_json(
        _ask_claude(PROFILE_PROMPT.format(qa_log="\n\n".join(qa_log)))
    )
    profile["qa_log"] = qa_log
    _save_state(qa_log, profile)

    print("\n你的求職者檔案:")
    print(f"  摘要:{profile['summary']}")
    print(f"  搜尋關鍵字:{', '.join(profile['search_keywords'])}")
    print(f"  硬性條件:{'、'.join(profile['hard_requirements']) or '無'}")
    print(f"  地點偏好:{profile.get('location_preference') or '不限'}")
    print(f"  遠距偏好:{profile.get('remote_preference') or '不限'}")
    print(f"  其他偏好:{'、'.join(profile['preferences']) or '無'}")
    return profile
