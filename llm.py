"""大模型接口：DeepSeek 写脚本，MiniMax 配音。只用标准库，key 从 .env 读取。"""
import json
import os
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env():
    path = os.path.join(ROOT, ".env")
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("DEEPSEEK_API_KEY", "MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_GROUP_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def has(key):
    return bool(load_env().get(key))


def _post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} 返回 {e.code}：{e.read().decode('utf-8', 'ignore')[:300]}")


# ---------------- DeepSeek ----------------
def deepseek_json(system, user, temperature=0.9):
    """让 DeepSeek 按 JSON 返回。返回 (dict, usage)。"""
    key = load_env().get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("没有 DeepSeek key：请在 .env 里填 DEEPSEEK_API_KEY")
    t = time.time()
    r = _post("https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {key}"}, {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }, timeout=180)
    content = r["choices"][0]["message"]["content"]
    usage = r.get("usage", {})
    usage["seconds"] = round(time.time() - t, 1)
    return json.loads(content), usage


# ---------------- MiniMax ----------------
MINIMAX_HOSTS = ["https://api.minimaxi.com", "https://api.minimax.cn", "https://api.minimax.io"]


def _minimax(path, body):
    env = load_env()
    key = env.get("MINIMAX_API_KEY")
    if not key:
        raise RuntimeError("没有 MiniMax key：请在 .env 里填 MINIMAX_API_KEY")
    first = env.get("MINIMAX_BASE_URL") or MINIMAX_HOSTS[0]
    hosts = [first.rstrip("/")] + [h for h in MINIMAX_HOSTS if h != first.rstrip("/")]
    gid = env.get("MINIMAX_GROUP_ID")
    last = None
    for h in hosts:
        url = h + path + (f"?GroupId={gid}" if gid else "")
        try:
            r = _post(url, {"Authorization": f"Bearer {key}"}, body)
        except Exception as e:  # 换个域名再试（国内 / 海外账号域名不同）
            last = e
            continue
        code = (r.get("base_resp") or {}).get("status_code", 0)
        if code == 1004:  # 鉴权失败，多半是域名和账号区域不匹配
            last = RuntimeError(f"MiniMax 鉴权失败（{h}）：{r['base_resp'].get('status_msg')}")
            continue
        if code != 0:
            raise RuntimeError(f"MiniMax 返回错误 {code}：{r['base_resp'].get('status_msg')}")
        return r
    raise last


def minimax_tts(text, out_path, voice_id, speed=1.0, model="speech-2.8-hd"):
    """生成配音，写成 mp3。返回 (秒数, 计费字符数)。"""
    r = _minimax("/v1/t2a_v2", {
        "model": model, "text": text, "stream": False, "language_boost": "English",
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1, "pitch": 0},
        "audio_setting": {"format": "mp3", "sample_rate": 44100, "bitrate": 128000, "channel": 1},
    })
    with open(out_path, "wb") as f:
        f.write(bytes.fromhex(r["data"]["audio"]))
    info = r.get("extra_info", {})
    return info.get("audio_length", 0) / 1000, info.get("usage_characters", len(text))


def minimax_voices():
    r = _minimax("/v1/get_voice", {"voice_type": "system"})
    return [v for v in r.get("system_voice", []) if v.get("voice_id", "").lower().startswith("english")]
