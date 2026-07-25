# 求職推薦系統(104 + 1111 + JobFrog + CakeResume)

結合爬蟲、RAG 與 Claude 的個人化職缺推薦工具。
每次執行會:讀履歷(選填)→ 訪談你(只追問履歷沒寫到的)→ 爬職缺 →
排除推薦過的 → 向量檢索 → Claude 精選並給理由 → 推播 Telegram → 記錄本次推薦。

## 安裝

```bash
pip install -r requirements.txt
playwright install chromium                # 1111 爬蟲需要無頭瀏覽器
export ANTHROPIC_API_KEY=sk-ant-你的金鑰   # Windows: set ANTHROPIC_API_KEY=...
```

## 執行

```bash
python main.py                  # 純問答收集求職偏好
python main.py 履歷.pdf          # 先讀履歷,只追問履歷沒寫到的資訊
```

首次執行會下載 BGE-M3 embedding 模型(約 2GB),之後就走本地快取。

### 設定 Telegram 推播(選填)

1. 跟 [BotFather](https://t.me/BotFather) 申請 Bot,取得 token,設定 `TELEGRAM_BOT_TOKEN`
2. 傳一則訊息給你的 Bot
3. 執行 `python notifier.py` 偵測並印出 chat_id,設定 `TELEGRAM_CHAT_ID`
4. 不設定的話,`main.py` 會略過推播,只在終端機輸出

## 專案結構

```
main.py               主流程
resume.py             履歷讀取(.pdf / .docx / .txt / .md)
interview.py          Claude 動態訪談(選擇題+簡答題)
crawlers/
  crawler_104.py      104 JSON 端點爬蟲
  crawler_1111.py     1111 HTML 解析爬蟲
  crawler_jobfrog.py  JobFrog(外商科技職缺)公司頁 HTML 解析爬蟲
  crawler_cakeresume.py  CakeResume 公司頁 __NEXT_DATA__ JSON 解析爬蟲
rag.py                embedding、Chroma 檢索、Claude 重排序
notifier.py            Telegram 推播
history.py             SQLite 推薦歷史去重
config.py              所有可調參數
```

## 常見調整

- 推薦數量 / 檢索數量:`config.py` 的 `FINAL_RECOMMEND_N`、`RETRIEVE_TOP_K`
- 爬取頁數:`MAX_PAGES_PER_KEYWORD`
- 省成本:`CLAUDE_MODEL` 改成 `claude-haiku-4-5-20251001`
- 清空推薦歷史:刪除 `history.db`

## 注意事項

- 104/1111 皆為非官方介面,網站改版時爬蟲需要更新(檔案內有註解說明怎麼修)
- 請保持合理的爬取頻率(預設每次請求間隔 1.5~3.5 秒),避免造成對方負擔或被封鎖
