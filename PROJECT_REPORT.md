# 求職推薦系統 —— 爬蟲 × RAG × Claude 個人化職缺推薦

> 整合履歷解析、多來源爬蟲、向量檢索(RAG)與 Claude API,針對台灣求職市場打造的
> 個人化職缺推薦工具。目標平台為 **104 人力銀行**、**1111 人力銀行**、**JobFrog**(外商科技職缺聚合站)、
> **CakeResume**(cake.me)。

專案位置:`C:\Users\PC\Desktop\job-recommender\`

## 專案動機

一般求職網站的「推薦職缺」只做關鍵字比對,既不理解求職者的真實背景與硬性條件,
也不記得使用者「已經看過哪些」——每次登入都在看重複的職缺。這個專案想解決兩件事:

- **語意層級的媒合**:不是關鍵字比對,而是用 Claude 分析履歷、追問缺漏資訊,
  彙整成結構化「求職者檔案」,再用向量檢索 + LLM 重排序找出真正契合的職缺
- **記憶能力**:用 SQLite 記錄每次推薦過的職缺,下次執行自動排除,讓系統「記得」使用者已經看過什麼

雙重目標:

- **實用價值** —— 真的能用來找工作,省下人工篩選履歷不合適職缺的時間
- **系統設計練習** —— 面對兩個會不定期改版、有反爬機制的外部網站,設計出能持續運作、
  好維護的爬蟲架構,以及善用 LLM 做結構化資訊萃取與排序的完整管線

## 📋 專題概覽

| 項目 | 說明 |
|---|---|
| 資料來源 | 104 人力銀行(JSON 端點)、1111 人力銀行(Playwright 渲染)、JobFrog(外商科技職缺)、CakeResume(公司頁 __NEXT_DATA__ JSON) |
| 履歷格式 | `.pdf` / `.docx` / `.txt` / `.md` |
| LLM | Anthropic Claude,`claude-sonnet-4-6`(可換 `claude-haiku-4-5-20251001` 省成本) |
| Embedding | 本地 `BAAI/bge-m3`(sentence-transformers,對中文效果好) |
| 向量庫 | ChromaDB,in-memory,每次執行重建 |
| 去重機制 | SQLite 雙層比對:job_id 精準比對 + 「公司::職稱」簽名 |
| 推薦輸出 | 兩類別(不限地點條件最佳 / 符合地點偏好)+ 職缺能力缺口摘要 |
| 推播管道 | Telegram Bot(選填,未設定則只印在終端機) |
| 介面 | CLI(核心模組已解耦,未來可換 Streamlit) |
| 技術棧 | Python 3.12、Anthropic SDK、ChromaDB、sentence-transformers、SQLite、Playwright、BeautifulSoup4 |

## 🔑 系統設計亮點

**兩類別推薦,不讓地點偏好埋沒好機會** —— 單一排序邏輯下,「地點不符」會直接把一個
待遇/成長機會很好的職缺擠掉。系統改成跑兩次 Claude 重排序:類別一完全不看地點,只看
硬性條件、技能契合度與待遇;類別二在符合硬性條件的前提下,嚴格鎖定使用者列出的縣市。
兩份清單一起輸出,使用者自己判斷要不要為了機會考慮通勤或搬遷。

**四個資料來源、四套完全不同的爬蟲策略** —— 104 有可用的 JSON 端點,直接打 API 最穩定;
1111 改版後變成純 JS 渲染 + 反爬驗證,改用 Playwright 無頭瀏覽器渲染;JobFrog 的搜尋頁
被 `robots.txt` 擋 `/api/`,改成爬「公司頁面」這種伺服器端渲染、且被允許爬取的路徑;
CakeResume 的搜尋頁則是被 Cloudflare 驗證關卡擋住(不碰、不繞過),改走同樣伺服器端
渲染的公司頁,而且公司頁內嵌了 Next.js 的 `__NEXT_DATA__` JSON,可以直接解析結構化資料,
不用像 JobFrog 一樣正規表示式硬解 HTML。四種應對方式沒有一套放諸四海皆準的模板,而是
逐一看清楚每個網站實際擋在哪一層再對症下藥。

**追問只問履歷沒寫到的** —— 履歷已經清楚寫明的資訊(例如年資、技能)不會重複詢問;
系統也刻意提醒 Claude:如果過去工作經驗跟目標職位方向不同(例如做過家教、餐飲,但目標是
AI/金融),不能把總工作年資直接當成「相關年資」,避免不相關的資歷誤導媒合結果。

**訪談有狀態記憶** —— 問答紀錄與求職者檔案存進 `profile_state.json`,下次執行偵測到
就不重問基本題,只請 Claude 出「全新」的追問(新技能、薪資調整、對上次推薦的回饋等),
訪談體驗隨著使用次數變得越來越短。

## 📁 專案結構

```
job-recommender/
├── main.py                 主流程串接
├── resume.py                履歷讀取(pypdf / python-docx / 純文字)
├── interview.py             Claude 動態訪談 + 彙整求職者檔案,含狀態記憶
├── jsonutil.py               容錯解析 Claude 回傳的 JSON(去圍欄 + 忽略結尾多餘文字)
├── crawlers/
│   ├── crawler_104.py       104 JSON 端點爬蟲
│   ├── crawler_1111.py      Playwright 渲染 + BeautifulSoup 解析
│   ├── crawler_jobfrog.py   JobFrog 公司頁 HTML 解析
│   └── crawler_cakeresume.py  CakeResume 公司頁 __NEXT_DATA__ JSON 解析
├── rag.py                    embedding、Chroma 檢索、Claude 兩類別重排序、能力缺口摘要
├── company_review.py         組出面試/薪水評價網站的搜尋連結(不爬取內容)
├── notifier.py                Telegram 推播 + chat_id 偵測
├── history.py                 SQLite 推薦歷史去重
├── config.py                  所有可調參數(API key、Telegram token 均從環境變數讀)
├── profile_state.json         上次訪談的問答紀錄與求職者檔案(自動產生)
└── history.db                  推薦歷史 SQLite(自動產生)
```

## 🧭 第一步:讀履歷與動態訪談

**檔案:** `resume.py`、`interview.py`

流程分兩種情境:

| 情境 | 行為 |
|---|---|
| 有帶履歷(`python main.py 履歷.pdf`) | Claude 讀履歷全文,只針對「履歷沒寫清楚」的項目出題(工作型態、目標職位、地點、期望薪資務必問到) |
| 無履歷 | 走六題固定基本題(工作型態 / 目標職位 / 地點 / 薪資 / 技能 / 年資) |
| 偵測到 `profile_state.json` | 不重問基本題,只請 Claude 出 2–3 題全新追問(新技能、薪資調整、對上次推薦的回饋) |

第一輪問完後,Claude 會再依回答內容動態出 2–3 題追問(公司規模、產業、加班接受度……),
選擇題與簡答題混搭,選擇題支援「打錯字但夾帶有效數字」的容錯解析。

最終彙整成結構化求職者檔案:

```json
{
  "summary": "100字內描述,含職位方向、技能、與目標職位相關的經驗程度",
  "search_keywords": ["職稱或技能關鍵字,3-5個"],
  "hard_requirements": ["真正不能妥協的條件,例如月薪至少45k"],
  "location_preference": "偏好地點,例如高雄市;不限則填「不限」",
  "remote_preference": "遠距/彈性偏好",
  "preferences": ["其他軟性偏好"]
}
```

## 🕷️ 第二步:四來源爬蟲

**檔案:** `crawlers/crawler_104.py`、`crawlers/crawler_1111.py`、`crawlers/crawler_jobfrog.py`、
`crawlers/crawler_cakeresume.py`

| 來源 | 技術 | 原因 |
|---|---|---|
| 104 | `requests` 打 JSON 端點 `/jobs/search/api/jobs` | 有穩定可用的官方前端 API,不需要渲染頁面 |
| 1111 | Playwright 無頭瀏覽器渲染後用 BeautifulSoup 解析 | 搜尋結果頁改版為純 JS 渲染 + 反爬驗證(altcha),單純 requests 只拿到空殼 HTML |
| JobFrog | `requests` 爬 `/companies/<slug>` 公司頁 | 搜尋頁 JS 渲染且 `robots.txt` 擋 `/api/`;公司頁是伺服器端渲染且被允許爬取 |
| CakeResume | `requests` 爬 `/companies/<slug>` 公司頁,解析內嵌的 `__NEXT_DATA__` JSON | 搜尋頁被 Cloudflare Managed Challenge 擋住(不碰、不繞過驗證);`robots.txt` 完全開放,公司頁是伺服器端渲染,且內嵌結構化 JSON 資料,不需要正規表示式硬解 HTML |

所有來源統一輸出同一個 job dict 格式(`job_id` / `platform` / `title` / `company` /
`location` / `salary` / `description` / `url`),下游模組不需要知道資料來自哪個平台。

爬蟲一律遵守節流(`config.CRAWL_DELAY_RANGE`,每次請求間隔 1.5~3.5 秒隨機),
新增來源前先看 `robots.txt`,遇到反爬驗證(Cloudflare 挑戰、CAPTCHA)一律不繞過,改找該站
是否有其他合法可爬取的路徑。JobFrog 因為沒有伺服器端關鍵字搜尋、職缺標題幾乎全英文,
不做字串過濾,直接把(有上限的)全站列表交給後續 RAG 語意檢索判斷相關性;CakeResume
同樣沒有伺服器端關鍵字搜尋(公司頁沒有搜尋參數),做法比照 JobFrog。

## 🗄️ 第三步:歷史去重

**檔案:** `history.py`

```
104 + 1111 + JobFrog 職缺
        ↓
job_id 精準比對(SQLite PRIMARY KEY)
        ↓
「公司::職稱」簽名比對 ← 擋掉重新刊登換 ID 的職缺
        ↓
本次真正的候選職缺(fresh)
```

雙層去重的原因:企業重新刊登職缺常常會拿到新的 job_id,單純比對 ID 會讓使用者
反覆看到同一個職缺。加一層「公司+職稱」簽名比對,能擋掉這種換皮重複。

## 🔍 第四步:向量檢索(RAG)

**檔案:** `rag.py`

```
職缺文字(職稱+公司+地點+薪資+描述)
    ↓ BAAI/bge-m3 embedding(本地)
Chroma in-memory 向量庫(每次執行重建)
    ↓ 用求職者 summary 檢索
Top-K 候選職缺(config.RETRIEVE_TOP_K)
```

職缺是每次即時爬取的,不需要跨執行持久化,所以向量庫選擇 in-memory、每次重建,
省去處理陳舊資料的複雜度。

## 🤖 第五步:Claude 兩類別重排序

**檔案:** `rag.py`

| 類別 | 邏輯 |
|---|---|
| 類別一:條件與機會最佳 | 完全不考慮地點/遠距偏好,只依硬性條件過濾 + 技能匹配度 + 錄取機會 + 待遇排序 |
| 類別二:符合你的偏好 | 在類別一排除的職缺之外,嚴格鎖定使用者提到的縣市(不做「鄰近縣市」放寬),優先有遠距/彈性空間的職缺 |

兩類別各自向 Claude 要求「違反硬性條件的職缺一律排除,即使湊不滿數量也一樣,
寧缺勿濫」,並各給每筆職缺 50 字內的推薦理由。

**程式碼層的雙重保險**(見下方挑戰 4、5):Claude 的排序不保證每次都完美遵守規則,
`rag.py` 加了兩道後處理過濾:自相矛盾偵測(理由裡寫「應排除」卻還在名單中)、
地點嚴格比對(結果地點必須包含使用者列出的縣市之一)。

## 📊 第六步:能力缺口摘要

**檔案:** `rag.py`(`generate_gap_summary`)

額外請 Claude 分析這次檢索到、跟求職者最相關的職缺(取樣數由 `config.GAP_SUMMARY_SAMPLE_SIZE`
控制,預設 50 筆,等於用滿 RAG 撈回來的候選池)常見要求哪些技能/工具/證照,對照求職者背景,
按職涯方向分領域(可能橫跨金融、AI/資料科學等多個領域)給出 2–4 項補強建議。這份摘要放在
推薦結果最後,是「找工作」之外額外附加的「怎麼讓自己更符合市場」的產出。

**建議紮根在實際職缺上,不是模型憑常識講空話** —— 早期版本只取樣 30 筆、描述只截 150 字,
建議容易流於「加強程式能力」這類空泛說法。現在每項建議要求 Claude 附上 `evidence`(依據的
職缺編號),`format_gap_summary` 會把引用的職缺數量一併顯示(例如「依據 3 筆相關職缺」),
prompt 也明講不能寫沒有具體名詞(工具/證照/專案方向)的建議。

## 📮 第七步:輸出與 Telegram 推播

**檔案:** `main.py`、`notifier.py`、`company_review.py`

終端機印出兩類別推薦 + 能力缺口總摘要,同時嘗試推播到 Telegram(未設定 token/chat_id
則自動略過,不影響其他步驟)。推播內容過長時依行切段,不硬切斷單則訊息內容
(Telegram 單則訊息上限 4096 字)。

每筆推薦職缺旁附上 `interview.tw` / `salary.tw` 的公司搜尋連結,方便使用者自己查
面試心得與薪水行情 —— 這兩個網站的公司搜尋功能被 `robots.txt` 明確擋爬取,系統只組
連結交給使用者手動點,不對它們發送任何自動化請求。

## ⚔️ 遇到的挑戰與解法

**挑戰 1 —— 104 端點改版**

舊的非官方端點 `/jobs/search/list` 已 404,回應結構也從 `{"data": {"list": [...]}}`
變成 `{"data": [...]}`,薪資從 `salaryDesc` 字串改成 `salaryLow`/`salaryHigh` 數字。

→ 用瀏覽器開發者工具側錄 Network 流量找到新端點 `/jobs/search/api/jobs`,重寫解析邏輯。
外部非官方介面的改版屬於預期內會定期發生的事,不是程式碼本身的 bug。

**挑戰 2 —— 1111 變成 JS 渲染 + 反爬驗證**

單純 `requests` 抓到的只是空殼 HTML(`<title>Loading...</title>`,沒有任何 `/job/` 連結)。

→ 改用 Playwright 開無頭瀏覽器把頁面渲染出來後再用 BeautifulSoup 解析,選擇器邏輯
(以 `/job/<id>` 連結為錨點的防禦性寫法)維持不變。

**挑戰 3 —— JobFrog 的 robots.txt 擋住搜尋 API**

搜尋頁完全 JS 渲染,但其 `/api/` 被 `robots.txt` 明確禁止爬取。

→ 改走 `/companies/<slug>` 這種伺服器端渲染、robots.txt 允許的頁面:先讀
`sitemap.xml` 拿到所有公司 slug,再逐一爬取,不需要 Playwright。

**挑戰 4 —— Claude 回傳 JSON 後面夾帶多餘文字**

即使 prompt 已要求「只回傳 JSON」,Claude 偶爾還是會在陣列後面補一段說明文字,
導致 `json.loads` 噴 `Extra data` 錯誤。

→ 抽成共用的 `jsonutil.parse_claude_json()`:去掉可能的 ` ```json ` 圍欄後,
用 `json.JSONDecoder().raw_decode()` 只取第一個合法 JSON 值,忽略後面多餘內容。
`interview.py`、`rag.py` 全部改用這個函式,不再各自 inline 剝圍欄。

**挑戰 5 —— Claude 為了湊數塞入自己都判定不合格的職缺**

prompt 已經明講「違反硬性條件一律排除,即使湊不滿數量也一樣」,但不保證每次都遵守——
偶爾會把職缺塞進結果,同時在推薦理由裡寫出「應排除」之類自相矛盾的字。

→ `rag.py` 的 `_SELF_EXCLUDE_MARKERS` 列表在程式碼層做保險:推薦理由包含
「應排除」「不符合硬性條件」等字樣就直接濾掉這筆結果,不完全依賴 prompt 約束。

**挑戰 6 —— 地點偏好被「貼心」放寬**

類別二要求嚴格鎖定使用者列出的縣市,但 Claude 有時會把鄰近縣市也算進去
(例如使用者說「新竹市」,結果混入「新竹縣」「苗栗縣」的職缺)。

→ 在程式碼裡從自由文字的地點偏好抓出明確提到的縣市名單(`TAIWAN_CITIES`),
重排序結果地點若不包含其中之一就過濾掉,不依賴模型自行判斷「算不算鄰近」。

**挑戰 7 —— 履歷年資會誤導媒合**

求職者履歷可能過去做的是家教、餐飲、行政等與目標職位無關的工作,如果直接把
「總工作年資」當成該目標領域的相關年資,會讓系統誤判資歷程度。

→ 在追問與彙整檔案的 prompt 中明確要求:年資務必寫「跟目標職位相關」的程度,
不相關的過去工作即使做了幾年,也要寫成應屆/新鮮人等級。

**挑戰 8 —— 每次執行都重問一樣的基本問題**

早期版本每次執行都要從頭跑完整訪談流程,對已經用過系統的使用者很煩。

→ 加入 `profile_state.json` 狀態記憶:問答紀錄與求職者檔案存檔,下次執行偵測到
就跳過基本題與履歷分析,只請 Claude 出全新的追問,累積在同一份問答紀錄上更新檔案。

## 📖 學到什麼

**技術面**

- 面對「非官方 API/會改版的外部依賴」的務實心態:先假設是對方變了,用瀏覽器
  開發者工具側錄真實 Network 流量找新端點,而不是先懷疑自己的程式碼
- 同一個資料抓取需求,依照網站的防禦手段(有無 API、是否 JS 渲染、robots.txt
  允許範圍)可能需要三種完全不同的技術解法,沒有萬用模板
- LLM 結構化輸出不能全信 prompt 約束——「只回傳 JSON」「不能違反硬性條件」
  這類指令都需要程式碼層的解析容錯與結果驗證作為第二道防線
- 有狀態的互動設計(訪談記憶)能大幅改善重複使用的體驗,狀態不必存資料庫,
  單一 JSON 檔案就足夠

**思維面**

- 「地點不符」不該是唯一的排序維度——拆成兩類別推薦,把「機會優先」與
  「生活品質優先」分開呈現,比硬塞進一套排序邏輯更貼近真實決策
- 對 LLM 的指令要假設「大部分時候會遵守,但不能保證每次都遵守」,關鍵規則
  (硬性條件、地點鎖定)要有程式碼層的事後驗證,而不是只靠寫得更嚴謹的 prompt
- 「總年資」在有落差的職涯轉換情境下是一個危險的預設值,必須明確定義成
  「跟目標領域相關」的年資,否則看似合理的欄位反而會誤導整個媒合結果

## ⚠️ 目前限制

| 限制 | 說明 |
|---|---|
| 1111 欄位不完整 | `company` / `location` 目前留空(卡片結構變動大,未解析),RAG 檢索與地點過濾對 1111 職缺因此失準 |
| JobFrog 無跨執行快取 | 每次執行都要重新爬取全部公司頁面,`JOBFROG_MAX_COMPANIES` 限制在 40 家 |
| CakeResume 每家公司只抓前 5 筆 | 公司頁伺服器端渲染只有前 5 筆職缺,其餘要點「Load more」用前端 JS 動態載入,目前沒找到對應公開 API;`CAKERESUME_MAX_COMPANIES` 限制在 40 家、同樣無跨執行快取 |
| 向量庫不持久化 | Chroma in-memory 每次重建,無法離線分析歷史職缺的向量分布 |
| Telegram 尚未完成設定 | BotFather 流程尚未走完,目前推播步驟會顯示「尚未設定,略過」 |
| 純 CLI 介面 | 尚未評估是否升級 Streamlit,核心模組已解耦,升級時只需替換 I/O 層 |

## 🚀 待辦(建議順序)

1. 帶使用者走完 Telegram BotFather 流程:申請 Bot → 設定 `TELEGRAM_BOT_TOKEN` →
   傳訊息給 Bot → 跑 `python notifier.py` 偵測 chat_id → 設定 `TELEGRAM_CHAT_ID` →
   重跑 `main.py` 確認真的收到推播
2. 跑第二次 `main.py`,確認 `history.db` 去重生效(前次推薦過的職缺不該再出現)
3. 補齊 1111 的 `company` / `location` 卡片解析,讓地點過濾對 1111 職缺同樣準確
4. 視執行效率調整 `JOBFROG_MAX_COMPANIES` / `CAKERESUME_MAX_COMPANIES`,評估是否需要跨執行快取
5. 視需求評估是否導入 Streamlit 介面

## 🛠 技術棧

Python 3.12 · Anthropic Claude API(`claude-sonnet-4-6`) · sentence-transformers
(`BAAI/bge-m3`) · ChromaDB · SQLite · Playwright · BeautifulSoup4 · requests ·
pypdf · python-docx · Telegram Bot API

## 🔗 執行方式

```bash
pip install -r requirements.txt
playwright install chromium
$env:ANTHROPIC_API_KEY = "sk-ant-你的金鑰"

python main.py                  # 純問答收集求職偏好
python main.py 履歷.pdf          # 先讀履歷,只追問履歷沒寫到的資訊
```

首次執行會下載 BGE-M3 embedding 模型(約 2GB),之後走本地快取。
