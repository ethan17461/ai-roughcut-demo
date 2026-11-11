"""把 pipeline.py 的输出整理成网页 Demo：index.html + audio/ + draft/"""
import glob, json, os, shutil
ROOT = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(ROOT, "output")
os.makedirs(os.path.join(ROOT, "audio"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "draft"), exist_ok=True)
for f in glob.glob(os.path.join(out, "tts", "*.m4a")):
    shutil.copy(f, os.path.join(ROOT, "audio", os.path.basename(f)))
d = glob.glob(os.path.join(out, "jianying_draft", "*", "draft_info.json"))[0]
shutil.copy(d, os.path.join(ROOT, "draft", "draft_info.json"))
result = open(os.path.join(out, "result.json"), encoding="utf-8").read()
tpl = open(os.path.join(ROOT, "web", "template.html"), encoding="utf-8").read()
review_path = os.path.join(ROOT, "data", "review", "review.json")
review = open(review_path, encoding="utf-8").read() if os.path.exists(review_path) else "null"   # 数据复盘的结果（review.py 生成）
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(
    tpl.replace("/*__RESULT__*/null", result).replace("/*__REVIEW__*/null", review))
print("index.html built")
