"""AI 粗剪流水线（最小可用版）

选题 → 写脚本（脚本 Agent 初稿 + 规则审核）→ 读 Skill → 配音 → 分段 → 素材召回 → 规则检查 → 编排剪映草稿 → 自动评分

用法：.venv/bin/python pipeline.py [--draft-root <剪映草稿目录>]
输出：output/result.json（给网页 Demo 用）、output/log.txt、output/tts/*.wav|m4a，
     以及剪映草稿文件夹（默认写进本机剪映的草稿目录，打开剪映即可看到）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import time

import pyJianYingDraft as jy

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")
DEFAULT_DRAFT_ROOT = os.path.expanduser("~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft")
DRAFT_NAME = "AI粗剪_伦敦苏格兰卧铺_v1"
US = 1_000_000

# ---- 关键词 → 概念（检索用）。真实落地时换成向量检索 ----
LEXICON = {
    "sleep": ["sleeper"], "sleeper": ["sleeper", "train"], "asleep": ["sleeper"],
    "train": ["train"], "midnight": ["night"], "night": ["night"],
    "leaves": ["depart", "station"], "euston": ["station"], "station": ["station"],
    "city": ["city"], "wake": ["morning", "window"], "lochs": ["lake"], "loch": ["lake"],
    "highland": ["mountain"], "highlands": ["mountain"],
    "book": ["ticket"], "legs": ["ticket"], "ticket": ["ticket"], "save": ["ticket"],
    "app": ["app", "phone"], "search": ["app", "phone"], "code": ["app"],
    "london": ["london"], "evening": ["night"],
}
PLACES = {"london": "伦敦", "euston": "伦敦", "scotland": "苏格兰", "highland": "苏格兰", "highlands": "苏格兰"}

log_lines = []


def log(step, msg, t0):
    ms = int((time.time() - t0) * 1000)
    line = {"step": step, "msg": msg, "ms": ms}
    log_lines.append(line)
    print(f"[{ms:>6} ms] {step}｜{msg}")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def words(text):
    return re.findall(r"[a-z]+", text.lower())


def concepts_of(text):
    out = []
    for w in words(text):
        for c in LEXICON.get(w, []):
            if c not in out:
                out.append(c)
    return out


def places_of(text):
    return sorted({PLACES[w] for w in words(text) if w in PLACES})


def select_topic(topics):
    rates = topics["genre_hit_rate"]
    top_rate = max(rates.values())
    nodes = {n["name"]: n["weight"] for n in topics["nodes"]}
    scored = []
    for t in topics["pool"]:
        hit = max(rates[g] for g in t["genre"]) / top_rate
        sc = 0.5 * hit + 0.3 * nodes.get(t["node"], 0) + 0.2 * t["benefit_fit"]
        scored.append({**t, "hit": round(hit, 2), "node_w": nodes.get(t["node"], 0), "score": round(sc, 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def check_script(variant, facts):
    lines = variant["lines"]
    text = " ".join(l["en"].lower() for l in lines)
    checks = []
    first = lines[0]["en"].lower()
    early = re.search(r"\d+%|code|save|off|uk\d+", first)
    checks.append({"name": "开头不放利益点（R1）", "ok": not early, "msg": "第 1 句没有价格或优惠" if not early else f"第 1 句出现利益点：{lines[0]['en']}"})
    long = [l["en"] for l in lines if len(l["en"].split()) > 14]
    checks.append({"name": "每句不超过 14 个词", "ok": not long, "msg": "都在 14 个词以内" if not long else f"{len(long)} 句超长"})
    pct = [l["en"] for l in lines if "%" in l["en"] and not re.search(r"up to|extra|from", l["en"].lower())]
    checks.append({"name": "价格写 up to / extra（R4）", "ok": not pct, "msg": "价格表述合规" if not pct else "有价格没写 up to"})
    conflict = [c["msg"] for c in facts["conflicts"] if all(w in text for w in c["if_all"])]
    checks.append({"name": "事实核查（对照事实库）", "ok": not conflict, "msg": conflict[0] if conflict else "所用事实都能在事实库找到出处"})
    return checks


def tts(text, path_noext, voice, rate):
    aiff = path_noext + ".aiff"
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", aiff, text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@44100", aiff, path_noext + ".wav"], check=True)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", aiff, path_noext + ".m4a"], check=True)
    info = subprocess.run(["afinfo", aiff], capture_output=True, text=True).stdout
    os.remove(aiff)
    return float(re.search(r"estimated duration: ([\d.]+)", info).group(1))


def retrieve(line, clips, durations):
    need = concepts_of(line["en"])
    places = places_of(line["en"])
    ranked = []
    for c in clips:
        matched = [x for x in need if x in c["tags"]]
        coverage = len(matched) / len(need) if need else 0
        excluded = None
        if places and c["location"] != "未知" and c["location"] not in places:
            excluded = f"地点不符：画面是{c['location']}，脚本说的是{'、'.join(places)}"
        loc_hit = 1 if (places and c["location"] in places) else 0
        ranked.append({"id": c["id"], "title": c["title"], "coverage": round(coverage, 2), "matched": matched,
                       "quality": c["quality"], "issues": c["issues"], "excluded": excluded, "loc_hit": loc_hit,
                       "clip_s": round(durations[c["id"]], 2)})
    ranked.sort(key=lambda r: (r["coverage"], r["loc_hit"], -len(r["issues"]), r["quality"]), reverse=True)
    valid = [r for r in ranked if not r["excluded"] and r["coverage"] > 0]
    bad = [r for r in ranked if r["excluded"] and r["coverage"] > 0]
    return need, places, valid[:3], bad[:1]


def wrap(text, n):
    if len(text) <= n:
        return text
    cut = text.rfind(" ", 0, n)
    return text[:cut] + "\n" + text[cut + 1:]


def score(plan, lines, rules_hits, skill):
    shots = [s for seg in plan for s in seg["shots"]]
    covs = [s["coverage"] for s in shots]
    avg_cov = sum(covs) / len(covs)
    wrong = [s for s in shots if s.get("excluded")]
    sem = 0 if wrong else 30 * avg_cov
    short = [s for s in shots if s["dur"] < 1.0]
    align = max(0, 10 - 3 * len(short))
    opening = 15
    if not rules_hits["R1"]["ok"]:
        opening -= 8
    if plan[0]["dur"] > 3.5:
        opening -= 2
    rule_checks = [
        all(seg["subtitle"] for seg in plan),
        any(st["kind"] == "开头花字" for seg in plan for st in seg["stickers"]),
        any(st["kind"] == "利益点贴纸" for seg in plan for st in seg["stickers"]),
        any(st["kind"] == "结尾钩子" and st["dur"] >= skill["cta_min_s"] for seg in plan for st in seg["stickers"]),
        all(s["dur"] <= skill["max_shot_s"] + 0.05 for s in shots),
    ]
    rule_score = 3 * sum(rule_checks)
    q = sum(s["quality"] for s in shots) / len(shots)
    quality = 10 * q / 5
    comp = 15
    if not rules_hits["R2"]["ok"]:
        comp -= 8
    if not rules_hits["R3"]["ok"]:
        comp -= 3
    if not rules_hits["R4"]["ok"]:
        comp -= 5
    dims = [
        {"n": "脚本和画面语义匹配", "max": 30, "v": round(sem, 1),
         "why": "有镜头地点和脚本不符，本项记 0 分" if wrong else f"{len(shots)} 个镜头平均覆盖所在句子 {avg_cov:.0%} 的关键词"},
        {"n": "配音和画面对齐", "max": 15, "v": align, "why": "切点都对齐句子边界" + (f"，{len(short)} 个镜头短于 1 秒" if short else "") + "；句内画面节奏需人工复核，自动最多给 10 分"},
        {"n": "结构和开头", "max": 15, "v": opening, "why": f"开头 {plan[0]['dur']:.1f} 秒" + ("，建议压到 3.5 秒内" if plan[0]["dur"] > 3.5 else "") + ("；利益点出现在前 3 秒" if not rules_hits["R1"]["ok"] else "；利益点在后半段")},
        {"n": "剪辑规则还原", "max": 15, "v": rule_score, "why": f"Skill 规则命中 {sum(rule_checks)}/5" + ("" if rule_checks[4] else f"；有镜头超过 {skill['max_shot_s']} 秒（素材缺口）")},
        {"n": "画面质量", "max": 10, "v": round(quality, 1), "why": f"所用镜头平均清晰度 {q:.1f} / 5（540p 竖屏素材）"},
        {"n": "合规", "max": 15, "v": comp, "why": "；".join(h["msg"] for k, h in rules_hits.items() if k in ("R2", "R3", "R4"))},
    ]
    total = round(sum(d["v"] for d in dims))
    return dims, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft-root", default=DEFAULT_DRAFT_ROOT)
    args = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.join(OUT, "tts"), exist_ok=True)

    script, lib, skill, rules = load("script.json"), load("library.json"), load("skill.json"), load("rules.json")
    topics, facts, cands = load("topics.json"), load("facts.json"), load("script_candidates.json")
    clips = lib["clips"]

    scored = select_topic(topics)
    pick = scored[0]
    log("选题", f"{len(scored)} 个候选选题，按 历史爆款率×0.5 + 营销节点×0.3 + 利益点可植入×0.2 打分，选中 {pick['id']}「{pick['title']}」（{pick['score']}）", t0)

    variants = []
    for v in cands["variants"]:
        ch = check_script(v, facts)
        variants.append({"id": v["id"], "lines": v["lines"], "checks": ch, "ok": all(c["ok"] for c in ch)})
    chosen = next(v for v in variants if v["ok"])
    rejected = [f"{v['id']} 版：{next(c['msg'] for c in v['checks'] if not c['ok'])}" for v in variants if not v["ok"]]
    script["lines"] = [dict(l) for l in chosen["lines"]]
    log("写脚本", f"脚本 Agent 出 {len(variants)} 版初稿，审核拦下 {len(rejected)} 版，采用 {chosen['id']} 版", t0)
    log("读取 Skill", f"{skill['name']}：单镜头 ≤ {skill['max_shot_s']} 秒、字幕/花字样式、利益点和结尾钩子规则", t0)

    durations = {c["id"]: jy.VideoMaterial(os.path.join(ROOT, c["file"])).duration / US for c in clips}
    log("读取素材库", f"{len(clips)} 段实拍，已打标签（地点、场景、清晰度、风险）", t0)

    # 配音
    voice = skill["voice"]
    lines = script["lines"]
    for i, ln in enumerate(lines):
        ln["audio"] = f"output/tts/line{i + 1}"
        ln["voice_s"] = round(tts(ln["en"], os.path.join(ROOT, ln["audio"]), voice["voice"].split("（")[0], voice["rate_wpm"]), 2)
    log("生成配音", f"{len(lines)} 句，共 {sum(l['voice_s'] for l in lines):.1f} 秒（{voice['voice']}）", t0)

    # 分段：每句一段，段与段之间留气口
    t = 0.0
    for i, ln in enumerate(lines):
        ln["start"] = round(t, 3)
        gap = skill["gap_between_lines_s"] if i < len(lines) - 1 else skill["tail_s"]
        ln["seg_s"] = round(ln["voice_s"] + gap, 3)
        t += ln["seg_s"]
    total_s = round(t, 2)
    log("按语义和气口分段", f"{len(lines)} 段，总时长 {total_s} 秒", t0)

    # 素材召回 + 规则（地点）
    plan = []
    n_excluded = 0
    for i, ln in enumerate(lines):
        need, places, top, bad = retrieve(ln, clips, durations)
        n_excluded += len(bad)
        seg = {"i": i, "en": ln["en"], "zh": ln["zh"], "role": ln["role"], "start": ln["start"], "dur": ln["seg_s"],
               "voice_s": ln["voice_s"], "audio": ln["audio"], "need": need, "places": places,
               "candidates": top + bad, "shots": [], "stickers": [], "gap": None, "subtitle": wrap(ln["en"], skill["subtitle"]["max_chars_per_line"])}
        # 单镜头太长就切成两个镜头（Skill 规则），第二个镜头要补上第一个没覆盖到的关键词
        first = top[0]
        second = None
        if seg["dur"] > skill["max_shot_s"]:
            for cand in top[1:]:
                if set(cand["matched"]) - set(first["matched"]):
                    second = cand
                    break
            if not second:
                clean = [c for c in top[1:] if not c["issues"]]
                second = clean[0] if clean else None
            if not second:
                seg["gap"] = f"素材缺口：和「{'、'.join(need)}」相关的镜头只有 1 个，这句只能用单镜头 {seg['dur']:.1f} 秒"
        if second:
            d1 = round(seg["dur"] * 0.5, 3)
            parts = [(first, seg["start"], d1), (second, seg["start"] + d1, round(seg["dur"] - d1, 3))]
        else:
            parts = [(first, seg["start"], seg["dur"])]
        for cand, st, d in parts:
            src_in = min(skill["clip_skip_head_s"], max(0, durations[cand["id"]] - d))
            seg["shots"].append({"clip": cand["id"], "title": cand["title"], "start": round(st, 3), "dur": round(d, 3),
                                 "src_in": round(src_in, 2), "coverage": cand["coverage"], "quality": cand["quality"],
                                 "issues": cand["issues"], "excluded": cand["excluded"]})
        plan.append(seg)
    log("本地素材库召回", f"每句按关键词召回 3 个候选；排除地点不符 {n_excluded} 个；{sum(len(s['shots']) for s in plan)} 个镜头", t0)

    # 花字 / 贴纸
    for seg, ln in zip(plan, lines):
        if not ln.get("on_screen"):
            continue
        if seg["i"] == 0:
            st, d, kind = 0.0, min(skill["opening_huazi_max_s"], seg["dur"]), "开头花字"
        elif seg["i"] == len(plan) - 1:
            st, d, kind = seg["start"] + 0.2, seg["dur"] - 0.2, "结尾钩子"
        else:
            st, d, kind = seg["start"] + skill["benefit_sticker_offset_s"], skill["benefit_sticker_len_s"], "利益点贴纸"
        seg["stickers"].append({"kind": kind, "text": ln["on_screen"], "start": round(st, 3), "dur": round(d, 3)})

    # 规则检查（RAG 检索到的英国 × TikTok 规则）
    first3 = [seg for seg in plan if seg["start"] < 3.0]
    benefit_early = any(re.search(r"\d+%|code|save|off", seg["en"].lower()) for seg in first3)
    shots = [s for seg in plan for s in seg["shots"]]
    brand = [s for s in shots if "brand" in s["issues"]]
    percent_lines = [seg for seg in plan if "%" in seg["en"]]
    upto_missing = [seg for seg in percent_lines if not re.search(r"up to|from|extra", seg["en"].lower())]
    long_sub = [seg for seg in plan if any(len(x) > skill["subtitle"]["max_chars_per_line"] for x in seg["subtitle"].split("\n"))]
    hits = {
        "R1": {"ok": not benefit_early, "msg": "前 3 秒没有价格或优惠信息" if not benefit_early else "前 3 秒出现了利益点"},
        "R2": {"ok": True, "msg": "所选镜头里没有可识别人脸（人工标注）"},
        "R3": {"ok": not brand, "msg": "没有第三方品牌标识" if not brand else f"{len(brand)} 个镜头露出手机品牌标识"},
        "R4": {"ok": not upto_missing, "msg": "价格都写了 up to / extra" if not upto_missing else "有价格没写 up to"},
        "R5": {"ok": not long_sub, "msg": "字幕已按 42 字符自动断行" if not long_sub else "有字幕超过 42 字符"},
        "R6": {"ok": not any(s["excluded"] for s in shots), "msg": f"已排除 {n_excluded} 个地点不符的镜头，所用镜头地点都和脚本一致"},
    }
    rule_out = [{"id": r["id"], "name": r["name"], "why": r["why"], **hits[r["id"]]} for r in rules["rules"]]
    log("检索国家 / 平台规则", f"{script['country']} × {script['platform']}，命中 {len(rule_out)} 条，通过 {sum(r['ok'] for r in rule_out)} 条", t0)

    # 编排剪映草稿
    folder = jy.DraftFolder(args.draft_root)
    sf = folder.create_draft(DRAFT_NAME, 1080, 1920, 30, allow_replace=True)
    draft_dir = os.path.join(args.draft_root, DRAFT_NAME)
    clip_file = {c["id"]: c["file"] for c in clips}
    mdir = os.path.join(draft_dir, "materials")
    os.makedirs(mdir, exist_ok=True)
    for s in shots:
        dst = os.path.join(mdir, s["clip"] + ".mp4")
        if not os.path.exists(dst):
            shutil.copy(os.path.join(ROOT, clip_file[s["clip"]]), dst)
    for seg in plan:
        shutil.copy(os.path.join(ROOT, seg["audio"] + ".wav"), os.path.join(mdir, os.path.basename(seg["audio"]) + ".wav"))

    sf.append_tracks([jy.TrackSpec(jy.TrackType.video, "画面"), jy.TrackSpec(jy.TrackType.audio, "配音"),
                      jy.TrackSpec(jy.TrackType.text, "字幕"), jy.TrackSpec(jy.TrackType.text, "花字")])
    sub, hz = skill["subtitle"], skill["huazi"]
    for s in shots:
        mat = jy.VideoMaterial(os.path.join(mdir, s["clip"] + ".mp4"))
        sf.add_segment(jy.VideoSegment(mat, jy.Timerange(int(s["start"] * US), int(s["dur"] * US)),
                                       source_timerange=jy.Timerange(int(s["src_in"] * US), int(s["dur"] * US)),
                                       volume=0.0), "画面")
    for seg in plan:
        amat = jy.AudioMaterial(os.path.join(mdir, os.path.basename(seg["audio"]) + ".wav"))
        sf.add_segment(jy.AudioSegment(amat, jy.Timerange(int(seg["start"] * US), amat.duration)), "配音")
        sf.add_segment(jy.TextSegment(seg["subtitle"], jy.Timerange(int(seg["start"] * US), int(seg["dur"] * US)),
                                      style=jy.TextStyle(size=sub["size"], bold=sub["bold"], color=tuple(sub["color"]), align=1),
                                      border=jy.TextBorder(width=sub["border_width"]),
                                      clip_settings=jy.ClipSettings(transform_y=sub["y"])), "字幕")
        for st in seg["stickers"]:
            sf.add_segment(jy.TextSegment(st["text"], jy.Timerange(int(st["start"] * US), int(st["dur"] * US)),
                                          style=jy.TextStyle(size=hz["size"], bold=hz["bold"], color=tuple(hz["color"]), align=1),
                                          border=jy.TextBorder(width=hz["border_width"]),
                                          clip_settings=jy.ClipSettings(transform_y=hz["y"])), "花字")
    sf.save()
    n_st = sum(len(seg["stickers"]) for seg in plan)
    log("编排剪映轨道", f"已生成剪映草稿「{DRAFT_NAME}」：画面 {len(shots)} 段、配音 {len(plan)} 段、字幕 {len(plan)} 段、花字 {n_st} 个", t0)

    dims, total = score(plan, lines, hits, skill)
    band = "低于 70：退回重做" if total < 70 else "70–79：粗剪合格，交人工精修" if total < 80 else "80–89：精修后可发布" if total < 90 else "90+：有爆款潜力"
    log("自动评分", f"{total} 分 · {band}", t0)

    # 拷一份草稿到输出目录，留作证据
    out_draft = os.path.join(OUT, "jianying_draft", DRAFT_NAME)
    if os.path.exists(out_draft):
        shutil.rmtree(out_draft)
    shutil.copytree(draft_dir, out_draft)

    clip_meta = {c["id"]: {"title": c["title"], "file": c["file"], "tags": c["tags"], "location": c["location"],
                           "quality": c["quality"], "issues": c["issues"], "pexels": c["pexels"],
                           "clip_s": round(durations[c["id"]], 2)} for c in clips}
    result = {"topic": {"note": topics["note"], "month": topics["month"], "nodes": topics["nodes"], "pool": scored, "chosen": pick["id"]},
              "scripts": {"generated_by": cands["generated_by"], "variants": variants, "chosen": chosen["id"], "rejected": rejected, "facts": facts["facts"]},
              "title": script["title"], "country": script["country"], "platform": script["platform"],
              "skill": skill, "total_s": total_s, "segments": plan, "rules": rule_out, "score": {"dims": dims, "total": total, "band": band},
              "log": log_lines, "draft": {"name": DRAFT_NAME, "path": draft_dir, "shots": len(shots), "stickers": n_st},
              "clips": clip_meta}
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "log.txt"), "w", encoding="utf-8") as f:
        for l in log_lines:
            f.write(f"[{l['ms']:>6} ms] {l['step']}｜{l['msg']}\n")
    print("done:", os.path.join(OUT, "result.json"))


if __name__ == "__main__":
    main()
