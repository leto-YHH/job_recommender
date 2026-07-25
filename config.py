"""全域設定"""
import os

# ── Anthropic ──────────────────────────────────────────────
# 請先設定環境變數:export ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"          # 想省成本可換 "claude-haiku-4-5-20251001"

# ── Telegram ───────────────────────────────────────────────
# 跟 BotFather 拿 token 後設定 TELEGRAM_BOT_TOKEN,
# 再執行 `python notifier.py` 偵測 chat_id,設定 TELEGRAM_CHAT_ID
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── GitHub ─────────────────────────────────────────────────
# 選填。設定後,第一次訪談(履歷分析)時會自動抓這個帳號的公開 repo 摘要
# 接在履歷後面一起分析。設定方式:$env:GITHUB_USERNAME = "你的帳號"
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")
GITHUB_MAX_REPOS = 8                        # 最多抓幾個公開 repo(依最近更新排序)

# ── Embedding ──────────────────────────────────────────────
EMBEDDING_MODEL = "BAAI/bge-m3"             # 本地跑,對中文效果好

# ── 爬蟲 ───────────────────────────────────────────────────
MAX_PAGES_PER_KEYWORD = 3                   # 每個關鍵字最多爬幾頁
JOBFROG_MAX_COMPANIES = 40                  # jobfrog 每次執行最多爬幾家公司的職缺列表
CAKERESUME_MAX_COMPANIES = 40               # cakeresume 每次執行最多爬幾家公司的職缺列表
CRAWL_DELAY_RANGE = (1.5, 3.5)              # 每次請求間隔秒數(隨機)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# ── RAG ────────────────────────────────────────────────────
RETRIEVE_TOP_K = 50                         # 向量檢索取回幾筆(要同時餵給兩類推薦,拉高一點)
FINAL_RECOMMEND_N_GENERAL = 10              # 類別一(不考慮偏好,條件與機會最佳)推薦幾筆
FINAL_RECOMMEND_N_PREFERRED = 10            # 類別二(加入地點/遠距偏好)推薦幾筆
GAP_SUMMARY_SAMPLE_SIZE = 50                # 能力缺口摘要取樣幾筆候選職缺(越多樣本建議越有代表性)

# ── 儲存 ───────────────────────────────────────────────────
DB_PATH = "history.db"                      # 推薦歷史 SQLite
CHROMA_PATH = "./chroma_db"                 # 向量資料庫目錄
PROFILE_STATE_PATH = "profile_state.json"   # 上次訪談的問答紀錄與檔案,下次執行用來避免重複發問
