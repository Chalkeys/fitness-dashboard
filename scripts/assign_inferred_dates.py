"""Assign continuous calendar dates to day-NNN exports from an anchor date."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path


def assign_dates(export_dir: Path, last_date: date, *, force: bool = False) -> int:
    paths = sorted(export_dir.glob("day-*.json"))
    records = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        day_number = document.get("day_number")
        if not isinstance(day_number, int) or day_number < 1:
            raise ValueError(f"{path.name}: day_number 必须是正整数")
        records.append((path, document, day_number))
    if not records:
        raise ValueError(f"没有找到 day-NNN.json：{export_dir}")
    max_day = max(day_number for _, _, day_number in records)
    expected_days = set(range(1, max_day + 1))
    actual_days = {day_number for _, _, day_number in records}
    if actual_days != expected_days:
        missing = sorted(expected_days - actual_days)
        raise ValueError(f"day_number 不连续，缺少：{missing}")

    for path, document, day_number in records:
        inferred = last_date - timedelta(days=max_day - day_number)
        inferred_text = inferred.isoformat()
        if document.get("date") not in (None, inferred_text) and not force:
            raise ValueError(f"{path.name}: 已有日期 {document['date']} 与推算日期不一致")
        document["date"] = inferred_text
        provenance = document.setdefault("provenance", {})
        note = provenance.get("notes") or ""
        note = note.replace("Calendar date and detailed training/nutrition history are unavailable.", "")
        note = note.replace("原始 exported_at 缺失；使用协议哨兵时间 1970-01-01T00:00:00Z。", "")
        inferred_note = f"日期根据 Day {max_day} = {last_date.isoformat()} 且期间连续无中断推算为 {inferred_text}；请复核。"
        provenance["notes"] = " ".join(part for part in (note.strip(), inferred_note) if part)
        for review in document.get("review", []):
            if review.get("field") == "day.date":
                review["note"] = "日期已按连续记录推算；请用原始日历确认。"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, default=Path("exports"))
    parser.add_argument("--last-date", type=date.fromisoformat, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    count = assign_dates(args.export_dir.resolve(), args.last_date, force=args.force)
    print(f"已为 {count} 个每日文件写入连续推算日期：{args.last_date.isoformat()} 为最后一天")


if __name__ == "__main__":
    main()
