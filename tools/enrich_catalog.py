"""按本条义项补词性；未覆盖的词或短语直接报错，避免悄悄丢失词性。"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 这些首词已经逐项对照现有词库；新资料出现新结构时必须重新检查。
VERB_HEADS = set("put carry take bring be contribute make broaden build improve lay come do stem lead have address tackle set establish provide raise encourage strengthen evaluate strike apply adopt serve play promote develop achieve cover control operate symbolize pass preserve conserve express enable remain reflect shorten connect learn respect understand offer show maintain fulfill care meet listen think identify verify allow adapt cultivate master foster turn seize judge stand work realize act sharpen distinguish gain designate rank originate brave bloom help facilitate support deal cope result give move prove benefit protect lower".split())
NOUN_HEADS = set("practical hands-on social positive potential over-reliance traditional cultural artistic wedding landscape flowers intangible technological artificial digital satellite high-precision china’s space technical remote scientific independent information false infrastructure high-speed transportation deep-water shipping port terminal large labor carbon convenient local economic regional high-quality living quality public elderly community home-delivery environmental sustainable people poverty basic classroom academic higher extracurricular professional career job critical problem-solving communication team time a an the sound achievable individual eye-catching diverse aids global superb healthy negative adverse".split())
VERB_FORMS = {
    "pushes": "第三人称单数", "listened": "过去式／过去分词", "acknowledged": "过去式／过去分词",
    "makes": "第三人称单数", "deserves": "第三人称单数", "reshaped": "过去式／过去分词",
    "mastered": "过去式／过去分词", "builds": "第三人称单数", "turns": "第三人称单数",
    "contributed": "过去式／过去分词",
}
SENSE_OVERRIDES = {
    "lead to": "导致；引起某种结果", "result in": "导致；结果是", "result from": "由……引起；源于",
    "give rise to": "引起；导致", "bring about": "带来；引起", "facilitate sth.": "促进某事；使某事更容易",
    "contribute to sth.": "有助于某事；促成某事", "help sb. (to) do": "帮助某人做某事",
    "enable sb. to do": "使某人能够做某事", "allow sb. to do": "允许某人做某事",
    "support sb. in doing": "支持某人做某事", "build a building": "建造一座建筑物",
    "superb artistic value": "极高的艺术价值", "global coverage and high-precision positioning": "全球覆盖与高精度定位",
}


def load_senses():
    senses = {}
    with (ROOT / "data" / "word-senses.tsv").open(encoding="utf-8", newline="") as source:
        for row in csv.reader(source, delimiter="\t"):
            if len(row) != 6:
                raise ValueError(f"Invalid sense row: {row}")
            word, code, label, meaning, context, other = row[0], row[1], row[2], row[3], row[4], row[5]
            senses[word] = {"pos": code, "posLabel": label, "meaning": meaning, "context": context, "otherPos": other}
    return senses


def phrase_grammar(answer):
    text = answer.lower()
    if text.startswith(("if left unchecked", "as living standards")):
        return "clause", "状语从句", "条件或时间状语结构"
    if text.startswith(("one major reason", "this ", "the main factor", "a case in point", "i once", "what i learned", "the figure", "the chart", "innovation plays", "balancing work and leisure is", "shortcuts around", "each small")):
        return "clause", "分句／句架", "包含主语和谓语的表达"
    if text.startswith("not only"):
        return "correlative", "关联结构", "连接两个并列成分"
    if text.startswith("indispensable rather"):
        return "adj. phr.", "形容词短语", "描述性质或必要程度"
    if text.startswith("of great importance"):
        return "prep. phr.", "介词短语", "可在句中作表语或定语"
    if text.startswith("thereby"):
        return "adv.", "副词结构", "引出前述行为造成的结果"
    if text.startswith(("owing to", "as a result of", "in my own experience", "with the development", "due to", "over the past", "in recent years", "at the click")):
        return "prep. phr.", "介词短语", "后接名词成分，或在句中作状语"
    if text.startswith(("as a result", "in turn", "for example")):
        return "adv. phr.", "副词性短语", "在句中作状语，衔接上下文"
    head = text.split()[0].rstrip(',')
    if head in {"ecological", "urban", "resource"}:
        return "n. phr.", "名词短语", "整体用作名词成分"
    if head in VERB_FORMS:
        return "v. phr.", "动词短语", VERB_FORMS[head]
    if head in VERB_HEADS:
        return "v. phr.", "动词短语", "本条按所示形式默写"
    if head in NOUN_HEADS:
        return "n. phr.", "名词短语", "整体用作名词成分"
    raise ValueError(f"Phrase needs explicit grammar review: {answer}")


def annotate(catalog):
    senses = load_senses()
    for card in catalog["cards"]:
        answer = card["answer"]
        key = answer.lower().strip().rstrip(".")
        # 分类以实际默写目标为准；同义词族的第一个目标也可能是单个单词。
        if key in senses:
            sense = senses[key]
            card.update({"pos": sense["pos"], "posLabel": sense["posLabel"], "promptMeaning": sense["meaning"],
                         "promptContext": sense["context"], "otherPos": sense["otherPos"],
                         "grammarNote": "标注本条考查义项的词性", "dictionaryUrl": "https://dictionary.cambridge.org/dictionary/english/" + key})
        elif card["kind"] == "sentence":
            card.update({"pos": "pattern" if card["template"] else "sentence", "posLabel": "句架" if card["template"] else "完整句子",
                         "promptMeaning": card["zh"], "promptContext": "", "otherPos": "", "grammarNote": "按本条参考句式默写"})
        elif card["kind"] == "word":
            raise ValueError(f"Word needs explicit sense review: {answer}")
        else:
            code, label, note = phrase_grammar(answer)
            card.update({"pos": code, "posLabel": label, "promptMeaning": SENSE_OVERRIDES.get(answer, card["zh"]),
                         "promptContext": "", "otherPos": "", "grammarNote": note})
    return catalog


def main():
    path = ROOT / "data" / "catalog.json"
    catalog = annotate(json.loads(path.read_text(encoding="utf-8")))
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    write_browser_metadata(catalog)
    print(f"Grammar annotated: {len(catalog['cards'])} entries")


def write_browser_metadata(catalog):
    """生成旧进程也能读取的静态补丁；两份数据均来自同一套标注。"""
    fields = ("pos", "posLabel", "promptMeaning", "promptContext", "otherPos", "grammarNote", "dictionaryUrl")
    metadata = {card["id"]: {field: card[field] for field in fields if field in card} for card in catalog["cards"]}
    path = ROOT / "public" / "assets" / "grammar.json"
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
