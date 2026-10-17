"""从用户 Markdown 生成可追溯词卡；不执行文档里的命令或指令。"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZH = re.compile(r"[\u4e00-\u9fff]")


def clean(text):
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "").replace("\\", "")).strip().strip('“”')


def logical_lines(text):
    """合并 Markdown 软换行，保留标题、表格和列表边界。"""
    blocks, pending = [], ""
    for line in text.splitlines():
        boundary = not line.strip() or re.match(r"^(?:#{1,6} |\||- |\d+\.\s|>|---)", line)
        if boundary:
            if pending:
                blocks.append(pending)
                pending = ""
            if line.strip():
                pending = line.strip()
        else:
            pending += " " + line.strip()
    if pending:
        blocks.append(pending)
    return blocks


def make_catalog(text):
    cards, seen = [], {}
    section, heading, headers = 0, "", []

    def add(en, zh, usage="", example="", kind=None, line=0, note="资料中的教学归纳"):
        en, zh, usage, example = map(clean, (en, zh, usage, example))
        example = re.sub(r"[（(]教学改写[）)]", "", example).strip()
        en = re.sub(r"\s*\((?:n\.|v\.|adj\.)(?:/v\.)?\)\s*$", "", en)
        if not en or not zh or ZH.search(en) or not re.search("[a-zA-Z]", en):
            return
        key = en.lower().rstrip(". ")
        if key in seen:
            old = seen[key]
            old["sources"].append({"heading": heading, "line": line})
            if example and not old["example"]:
                old["example"] = example
            if usage and usage not in old["usage"]:
                old["usage"] = (old["usage"] + "；" + usage).strip("；")
            return
        kind = kind or ("word" if " " not in en else "phrase")
        template = bool(re.search(r"\[|…|\.\.\.|\bsb\.?\b|\bsth\.?\b|\b[A-BXY]\b|/|;|,", en)) and kind != "sentence"
        # 省略号/占位符的句架可临摹；完整句子可据中文默写。
        if "[" in en or "…" in en or "..." in en:
            template = True
        answer = re.split(r"\s+/\s+|;", en)[0].strip()
        # 紧凑斜杠属于共享前后缀的可选词：build/boost confidence -> build confidence。
        answer = " ".join(word.split("/")[0] for word in answer.split())
        answer = re.sub(r"\s*\([A-Z]{2,}\)", "", answer)
        # 这两处斜杠连接的是完整动词短语，不能按单个 token 拆分。
        if en.startswith("pass down/carry forward"):
            answer = en.replace("pass down/carry forward", "pass down")
        answer = answer.replace('“', '').replace('”', '')
        # 同义写法已选为具体表达后可以正常默写；只有真正的占位符才避开默认队列。
        template = bool(re.search(r"\[|…|\.\.\.|\bsb\.?\b|\bsth\.?\b|\b[A-BXY]\b", answer))
        card = {"id": hashlib.sha256(key.encode()).hexdigest()[:20], "en": en, "answer": answer, "zh": zh,
                "usage": usage, "example": example, "kind": kind, "template": template,
                "category": "翻译词汇" if section in (6, 7, 14) else "写作表达",
                "topic": re.sub(r"^\d+(?:\.\d+)?\.?\s*", "", heading), "note": note,
                "sources": [{"heading": heading, "line": line}]}
        cards.append(card)
        seen[key] = card

    lines = logical_lines(text)
    for index, raw in enumerate(lines, 1):
        if raw.startswith("## "):
            match = re.match(r"## (\d+)\.", raw)
            section = int(match[1]) if match else 0
        if raw.startswith("#"):
            heading = re.sub(r"^#+\s*", "", raw)
            headers = []
            continue
        if raw.startswith("|"):
            cells = [clean(c) for c in raw.strip().strip("|").split("|")]
            if all(re.fullmatch(r"[-: ]+", c or " ") for c in cells):
                continue
            if not headers:
                headers = cells
                continue
            if len(cells) != len(headers):
                continue
            row = dict(zip(headers, cells))
            if section == 4:
                add(cells[0], cells[1], cells[2] if len(cells) == 4 else "", cells[-1], line=index)
            elif section in (6, 7):
                add(cells[1], cells[0], cells[2] if section == 7 else "", cells[2] if section == 6 else "", line=index)
            elif section == 13:
                add(cells[0], cells[1], cells[2], cells[3], line=index, note="资料标注的参考范文短摘录；未重新独立核验原网页")
            elif section == 14 and len(cells) == 5:
                add(cells[1], cells[2], cells[3], line=index, note="资料标注的参考译文短摘录；未重新独立核验原网页")
            elif section == 14:
                add(cells[1], cells[0], "；".join(cells[2:]), line=index)
            elif section == 15:
                # 15.9 是中文在前，其他小节均为英文在前。
                if headers[0] == "中文":
                    add(cells[1], cells[0], cells[2], line=index)
                else:
                    add(cells[0], cells[1], cells[2] if len(cells) >= 3 else "", cells[3] if len(cells) == 4 else "", line=index)
            continue
        headers = []
        if section == 2:
            match = re.match(r"\d+\.\s+\*\*(.*?)\*\*\s*(.+)", raw)
            if match:
                meaning = clean(match[2])
                end = meaning.find("。")
                usage = meaning[end + 1:].strip() if end >= 0 else ""
                meaning = meaning[:end + 1] if end >= 0 else meaning
                add(match[1], meaning, usage=usage, kind="sentence", line=index, note="资料中的可迁移句架；方括号内容需要替换")
        elif section == 5:
            match = re.match(r"-\s+(.+?[a-zA-Z…])\s+([\u4e00-\u9fff].+)", raw)
            if match:
                add(match[1], match[2], line=index)
        elif section == 10 or (section == 6 and "6.5" in heading):
            match = re.match(r"-\s+\*\*(.+?)\*\*[：:]\s*(.+)", raw)
            if match:
                add(match[1], match[2], line=index)
            reverse = re.match(r"-\s+([^：]+)：\*\*(.+?)\*\*", raw)
            if reverse and ZH.search(reverse[1]):
                add(reverse[2], reverse[1], line=index)
        elif section == 14 and "14.3" in heading:
            match = re.search(r"`([^`]+)`\s*—\s*(.+)", raw)
            if match:
                add(match[1], match[2], kind="sentence", line=index)
    # 将真实完整例句提升为独立句子练习，中文只使用资料中已给的关键词含义。
    # 没有整句中译时，明确标记为语境提示，避免伪造原文翻译。
    for card in list(cards):
        example = card["example"]
        if re.fullmatch(r"[A-Z][^\u4e00-\u9fff]+[.!?]", example) and len(example.split()) >= 5:
            heading = card["sources"][0]["heading"]
            section = 7 if card["category"] == "翻译词汇" else 4
            add(example, "语境提示：" + card["zh"], usage="关键词：" + card["en"], kind="sentence",
                note="资料中的教学例句；中文为关键词提示，并非整句译文")
    # 第 8 节完整句子保留句型含义作为提示，不假称整句翻译。
    section, heading = 8, ""
    for index, raw in enumerate(lines, 1):
        if raw.startswith("## "):
            match = re.match(r"## (\d+)\.", raw)
            section = int(match[1]) if match else 0
        if section == 8 and raw.startswith("### "):
            heading = raw[4:]
        if section == 8 and raw.startswith("- "):
            sentence = clean(raw[2:])
            if not ZH.search(sentence) and sentence.endswith("."):
                hint = re.search(r"（(.+)）", heading)
                add(sentence, "句型提示：" + (hint[1] if hint else heading), kind="sentence", line=index,
                    note="资料中的教学例句；中文为句型提示，并非整句译文")
    return {"version": 1, "title": "CET-6 写作与翻译表达库", "cards": cards,
            "source": "CET6_近十年写作翻译范文与高频表达.md",
            "sourceSha256": hashlib.sha256(text.encode()).hexdigest(),
            "notes": ["参考范文不是官方唯一答案", "句架含占位符时仅临摹，不作为完整译文评分", "近十年与高频为用户资料的编排名称，不是独立频率统计"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    catalog = make_catalog(args.source.read_text(encoding="utf-8-sig"))
    translations_path = ROOT / "data" / "sentence-translations.json"
    if translations_path.exists():
        translations = json.loads(translations_path.read_text(encoding="utf-8"))
        for card in catalog["cards"]:
            translation = translations.get(card["id"])
            if translation and translation["en"] == card["en"]:
                card["originalHint"] = card["zh"]
                card["zh"] = translation["zh"]
                card["note"] = "原资料英文例句；中文为本站新增教学译文，可有其他正确译法"
    from enrich_catalog import annotate, write_browser_metadata
    catalog = annotate(catalog)
    write_browser_metadata(catalog)
    target = ROOT / "data" / "catalog.json"
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cards": len(catalog["cards"]), "sentences": sum(c["kind"] == "sentence" for c in catalog["cards"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
