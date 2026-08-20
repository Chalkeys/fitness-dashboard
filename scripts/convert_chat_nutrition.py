"""Convert a ChatGPT nutrition conversation export into reviewable records.

The ChatGPT Exporter format is conversational, not an import format.  This
script creates a safe staging file: daily totals are reused from existing
daily exports when available, while food mentions are extracted as
needs-review candidates.  It never calls the Xunji API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path.home() / "Downloads" / "ChatGPT-饮食记录与跟踪.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data_sources" / "chat_nutrition_staging.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "chat_nutrition_conversion.json"
ANCHOR_DATE = date(2026, 6, 22)  # Day 1 used by the existing daily exports.

FOOD_TERMS = (
    "酸奶",
    "oikos",
    "蛋白粉",
    "protein",
    "香蕉",
    "granola",
    "oat bran",
    "bran",
    "开心果",
    "鸡胸",
    "tyson",
    "虾",
    "shrimp",
    "米",
    "rice",
    "wrap",
    "tortilla",
    "ciabatta",
    "鸡蛋",
    "牛奶",
    "latte",
    "樱桃",
    "西瓜",
    "蓝莓",
    "牛肉干",
    "beef jerky",
    "沙丁鱼",
    "sardine",
    "金枪鱼",
    "tuna",
    "猪",
    "排骨",
    "鱼",
    "豆腐",
    "玉米",
    "taco",
    "寿司",
    "馅饼",
    "仙贝",
    "crumpet",
    "omelet",
    "honeydew",
    "饼干",
    "冰淇淋",
    "pâté",
    "肝酱",
)

NAME_ALIASES = {
    "bran": "Oat Bran",
    "oat bran": "Oat Bran",
    "生米饭": "生米",
    "米饭": "熟米饭",
    "latte": "Latte",
    "oikos": "Oikos Triple Zero",
}

MEAL_WORDS = {
    "早餐": "breakfast",
    "早饭": "breakfast",
    "午餐": "lunch",
    "午饭": "lunch",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "夜宵": "snack",
    "加餐": "snack",
    "零食": "snack",
    "中午": "lunch",
    "下午": "snack",
}

NEGATION_OR_META = (
    "没吃",
    "不吃",
    "不喝",
    "不是",
    "取消",
    "剔除",
    "换成",
    "修正",
    "固定",
    "按之前",
    "成分表",
    "营养表",
    "是不是",
    "能不能",
    "如果",
    "建议",
    "以后",
    "总结",
    "目标",
    "还差",
    "怎么算",
    "怎么记录",
    "导出",
    "偶尔",
    "包括",
    "需要",
    "多少",
    "给出",
    "营养",
    "按",
)

UNIT_MAP = {
    "克": "g",
    "g": "g",
    "公斤": "kg",
    "kg": "kg",
    "毫升": "ml",
    "ml": "ml",
    "个": "piece",
    "只": "piece",
    "片": "slice",
    "包": "bag",
    "袋": "bag",
    "瓶": "bottle",
    "杯": "cup",
    "罐": "can",
    "盒": "box",
    "份": "serving",
    "根": "piece",
    "块": "piece",
}

QUANTITY_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|ml|公斤|克|毫升|个|只|片|包|袋|瓶|杯|罐|盒|份|根|块)"
    r"|[×x]\s*(?P<count>\d+(?:\.\d+)?)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--anchor-date", default=ANCHOR_DATE.isoformat())
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u200b", " ")).strip()


def inferred_day(message_time: str, anchor: date) -> tuple[int, str]:
    timestamp = datetime.strptime(message_time, "%m/%d/%Y, %I:%M:%S %p")
    message_date = timestamp.date()
    return (message_date - anchor).days + 1, message_date.isoformat()


def meal_type(text: str, fallback: str = "unspecified") -> str:
    for marker, value in MEAL_WORDS.items():
        if marker in text:
            return value
    lowered = text.lower()
    if "breakfast" in lowered:
        return "breakfast"
    if "lunch" in lowered:
        return "lunch"
    if "dinner" in lowered:
        return "dinner"
    return fallback


def food_like(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in FOOD_TERMS)


def actual_food_input(text: str) -> bool:
    """Return true only for a likely consumed-food statement, not a correction."""
    if not food_like(text):
        return False
    if any(marker in text for marker in NEGATION_OR_META):
        return False
    if "默认" in text:
        return False
    if "照常" in text and not re.search(r"(?:\+|追加|增加)\s*\d", text, re.I):
        return False
    return bool(QUANTITY_RE.search(text) or re.search(r"吃了|喝了|吃|喝|还有|加了|追加|晚饭|午饭|早餐|晚餐|加餐", text, re.I))


def parse_amount(segment: str) -> tuple[float | None, str | None, str]:
    match = QUANTITY_RE.search(segment)
    if match:
        if match.group("count") is not None:
            amount = float(match.group("count"))
            return amount, "piece", QUANTITY_RE.sub("", segment, count=1)
        amount = float(match.group("amount"))
        unit = UNIT_MAP[match.group("unit").lower()]
        return amount, unit, QUANTITY_RE.sub("", segment, count=1)
    chinese_counts = {
        "一个": (1.0, "piece"), "一份": (1.0, "serving"), "一瓶": (1.0, "bottle"),
        "一杯": (1.0, "cup"), "一罐": (1.0, "can"), "一块": (1.0, "piece"),
        "一片": (1.0, "slice"), "两杯": (2.0, "cup"), "两份": (2.0, "serving"),
        "两个": (2.0, "piece"),
    }
    for marker, (amount, unit) in chinese_counts.items():
        if marker in segment:
            return amount, unit, segment.replace(marker, "", 1)
    return None, None, segment


def parse_food_segments(text: str, source_time: str, day_number: int, prefix: str) -> list[dict[str, Any]]:
    if not food_like(text):
        return []
    cleaned = normalize_text(text)
    incremental_bran = re.search(r"(?:oat\s*)?bran\s*\+\s*(\d+(?:\.\d+)?)\s*g", cleaned, re.I)
    if incremental_bran:
        amount = float(incremental_bran.group(1))
        return [{
            "entry_id": f"chat-day-{day_number:03d}-{prefix}-001",
            "meal_type": meal_type(text),
            "food_name": "Oat Bran",
            "amount": int(amount) if amount.is_integer() else amount,
            "unit": "g",
            "servings": None,
            "calories": None,
            "protein_g": None,
            "total_carbs_g": None,
            "fiber_g": None,
            "net_carbs_g": None,
            "fat_g": None,
            "notes": "相对于默认早餐的增量；需要确认默认早餐是否同时计入。",
            "status": "needs_review",
            "source_time": source_time,
            "source_text": cleaned,
        }]
    cleaned = re.sub(r"^(今天|今日|再|还|然后|另外|新增|加了|吃了|喝了|记录)\s*", "", cleaned)
    pieces = re.split(r"\s*(?:\+|、|，|,|；|;|\band\b|和)\s*", cleaned, flags=re.IGNORECASE)
    entries: list[dict[str, Any]] = []
    for piece in pieces:
        piece = piece.strip(" ：:。.!！？")
        if len(piece) < 2 or not food_like(piece):
            continue
        amount, unit, name = parse_amount(piece)
        name = re.sub(r"^[✅❌🍽️🥤🍌🌾🔥💪🍚🥑🌾⚡\s]+", "", name)
        for _ in range(3):
            name = re.sub(r"^(今天|今日|早餐|早饭|午餐|午饭|晚餐|晚饭|加餐|中午|下午|早上|睡前|新增|再加|又加了|加了|加|吃了|吃|喝了|喝|我吃了|我喝了|还有|有|是|我还|那个|这个|但是)\s*", "", name)
        name = re.sub(r"\s+", " ", name).strip(" ：:。.!！？")
        name = re.sub(r"(呢|吧)$", "", name).strip()
        if len(name) < 2 and name not in {"虾", "米", "鱼"}:
            continue
        if name in {"这个", "那个", "今天早餐", "默认早餐"}:
            continue
        if any(marker in name for marker in ("偶尔", "包括", "需要", "多少", "给出", "营养", "怎么", "记录", "常吃", "减", "喝的是")):
            continue
        name = NAME_ALIASES.get(name.lower(), name)
        entries.append(
            {
                "entry_id": f"chat-day-{day_number:03d}-{prefix}-{len(entries) + 1:03d}",
                "meal_type": meal_type(text),
                "food_name": name,
                "amount": int(amount) if amount is not None and amount.is_integer() else amount,
                "unit": unit,
                "servings": None,
                "calories": None,
                "protein_g": None,
                "total_carbs_g": None,
                "fiber_g": None,
                "net_carbs_g": None,
                "fat_g": None,
                "notes": "从聊天文本提取；需要根据食品标签或用户确认补齐营养值。",
                "status": "needs_review",
                "source_time": source_time,
                "source_text": normalize_text(piece),
            }
        )
    return entries


def existing_totals(day_number: int) -> dict[str, Any] | None:
    path = PROJECT_ROOT / "exports" / f"day-{day_number:03d}.json"
    if not path.exists():
        return None
    document = load_json(path)
    daily = document.get("daily_log") or {}
    if daily.get("calories_in") is None and daily.get("protein_g") is None:
        return None
    return {
        "calories_in": daily.get("calories_in"),
        "protein_g": daily.get("protein_g"),
        "total_carbs_g": daily.get("total_carbs_g"),
        "fiber_g": daily.get("fiber_g"),
        "net_carbs_g": daily.get("net_carbs_g"),
        "fat_g": daily.get("fat_g"),
        "source": "existing_daily_export",
    }


def final_text_for_day(messages: list[dict[str, Any]], day_number: int) -> tuple[str | None, str | None]:
    candidates: list[tuple[datetime, str, str]] = []
    marker = re.compile(rf"(?is)\bDay\s*{day_number}\b")
    final_marker = re.compile(r"(?i)最终|最终汇总|最终记录|最终累计|最终确认|正式归档")
    for message in messages:
        if message.get("role") != "Response":
            continue
        text = message.get("say", "")
        if marker.search(text) and final_marker.search(text):
            timestamp = datetime.strptime(message["time"], "%m/%d/%Y, %I:%M:%S %p")
            candidates.append((timestamp, message["time"], text))
    if not candidates:
        return None, None
    _, source_time, text = sorted(candidates)[-1]
    return text, source_time


def extract_metric(text: str, labels: str) -> float | None:
    values = re.findall(rf"(?:{labels})\s*[:：]?\s*[≈~]?\s*([\d,]+(?:\.\d+)?)", text, flags=re.I)
    if not values:
        return None
    return float(values[-1].replace(",", ""))


def chat_final_totals(messages: list[dict[str, Any]], day_number: int) -> dict[str, Any] | None:
    """Read totals only from an explicit final-summary response for this day."""
    candidates: list[tuple[datetime, str, str]] = []
    marker = re.compile(rf"(?is)\bDay\s*{day_number}\b[^\r\n]{{0,40}}(?:最终|最终汇总|最终累计|最终记录)")
    for message in messages:
        if message.get("role") != "Response":
            continue
        text = message.get("say", "")
        if not marker.search(text):
            continue
        if any(meta in text for meta in ("conversations.json", "导出以后", "不能保证做到完整", "永久数据库")):
            continue
        timestamp = datetime.strptime(message["time"], "%m/%d/%Y, %I:%M:%S %p")
        candidates.append((timestamp, message["time"], text))
    if not candidates:
        return None
    _, source_time, text = sorted(candidates)[-1]
    totals = {
        "calories_in": extract_metric(text, "热量|摄入热量|总热量"),
        "protein_g": extract_metric(text, "蛋白质|蛋白"),
        "total_carbs_g": extract_metric(text, r"(?<!净)(?:总碳水|碳水)"),
        "fiber_g": extract_metric(text, "膳食纤维|纤维"),
        "net_carbs_g": extract_metric(text, "净碳水"),
        "fat_g": extract_metric(text, "脂肪"),
        "source": "chat_final_summary",
        "source_time": source_time,
    }
    if totals["calories_in"] is None and totals["protein_g"] is None:
        return None
    return totals


def extract_final_entries(text: str | None, source_time: str | None, day_number: int) -> list[dict[str, Any]]:
    if not text or not source_time:
        return []
    entries: list[dict[str, Any]] = []
    section = "unspecified"
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = normalize_text(line)
        if not line:
            continue
        current_meal = meal_type(line, "")
        if current_meal:
            section = current_meal
            if line in MEAL_WORDS or line.rstrip("：:") in MEAL_WORDS:
                continue
        parsed = parse_food_segments(line, source_time, day_number, f"final-{line_number:03d}")
        for entry in parsed:
            entry["meal_type"] = section
            entries.append(entry)
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in entries:
        key = (entry["meal_type"], entry["food_name"].lower(), entry["amount"], entry["unit"])
        unique.setdefault(key, entry)
    return list(unique.values())


def build_records(messages: list[dict[str, Any]], anchor: date) -> tuple[list[dict[str, Any]], list[str]]:
    by_day: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    observed_days: set[int] = set()
    for message in messages:
        if not message.get("time"):
            continue
        day_number, date_value = inferred_day(message["time"], anchor)
        if day_number < 1 or day_number > 45:
            continue
        if message.get("role") == "Prompt" and food_like(message.get("say", "")):
            record = by_day.setdefault(
                day_number,
                {
                    "day_number": day_number,
                    "date": date_value,
                    "daily_totals": existing_totals(day_number),
                    "entries": [],
                    "raw_food_mentions": [],
                    "status": "needs_review",
                    "notes": [],
                },
            )
            observed_days.add(day_number)
            raw = normalize_text(message["say"])
            record["raw_food_mentions"].append(
                {"time": message["time"], "text": raw, "meal_type": meal_type(raw)}
            )
            if actual_food_input(raw):
                record["entries"].extend(parse_food_segments(raw, message["time"], day_number, f"prompt-{len(record['raw_food_mentions']):03d}"))
    if observed_days:
        for day_number in range(min(observed_days), max(observed_days) + 1):
            date_value = (anchor + timedelta(days=day_number - 1)).isoformat()
            by_day.setdefault(
                day_number,
                {
                    "day_number": day_number,
                    "date": date_value,
                    "daily_totals": existing_totals(day_number),
                    "entries": [],
                    "raw_food_mentions": [],
                    "status": "needs_review",
                    "notes": [],
                },
            )
    for day_number, record in by_day.items():
        if record["daily_totals"] is None:
            record["daily_totals"] = chat_final_totals(messages, day_number)
        if record["entries"]:
            record["notes"].append("明细来自用户实际输入；修改、删除和替换语句未自动写入。仍需人工确认后才能同步。")
        else:
            record["notes"].append("未自动提取到明确的用户食物明细。")
        if record["daily_totals"] is None:
            warnings.append(f"Day {day_number} 缺少现有标准导出中的每日营养总计。")
        if not record["entries"]:
            warnings.append(f"Day {day_number} 没有可审核的食物明细。")
        record["entry_count"] = len(record["entries"])
        record["raw_mention_count"] = len(record["raw_food_mentions"])
        record["sync_ready"] = False
        record["raw_food_mentions"] = record["raw_food_mentions"][:50]
        record.pop("source_messages", None)
    return [by_day[key] for key in sorted(by_day)], warnings


def convert(input_path: Path, output_path: Path, report_path: Path, anchor: date) -> dict[str, Any]:
    payload = load_json(input_path)
    messages = payload.get("messages", [])
    records, warnings = build_records(messages, anchor)
    food_counts = Counter(
        entry["food_name"] for record in records for entry in record.get("entries", [])
    )
    result = {
        "protocol": "chat_nutrition_records_v1",
        "source": {
            "filename": input_path.name,
            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "message_count": len(messages),
            "exported_at": payload.get("metadata", {}).get("dates", {}).get("exported"),
        },
        "anchor_date": anchor.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "food_candidates": [
            {"food_name": name, "mention_count": count, "status": "needs_review"}
            for name, count in sorted(food_counts.items())
        ],
        "warnings": warnings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "source": result["source"],
        "records": len(records),
        "records_with_totals": sum(bool(record.get("daily_totals")) for record in records),
        "records_with_entries": sum(bool(record.get("entries")) for record in records),
        "entry_candidates": sum(record.get("entry_count", 0) for record in records),
        "sync_ready_records": 0,
        "warnings": warnings,
        "output": str(output_path),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"找不到聊天导出文件：{args.input}")
    report = convert(args.input, args.output, args.report, date.fromisoformat(args.anchor_date))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
