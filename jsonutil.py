"""容錯解析 Claude 回傳的 JSON

即使 prompt 已經要求「只回傳 JSON」,Claude 有時還是會加上
```json 圍欄,或在 JSON 後面補一段說明文字。這裡去掉可能的圍欄,
並用 raw_decode 只取第一個合法 JSON 值,忽略後面多餘的內容。
"""
import json


def parse_claude_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        cleaned = cleaned.removeprefix("json").strip()
    return json.JSONDecoder().raw_decode(cleaned)[0]
