# AGENTS.md

给 Codex 等 AI 编程助手看的项目说明。改代码前先读这一页。

## 项目是什么

AI 产品经理课程的模拟项目：给一家做出海火车票短视频引流的业务方，做"AI 粗剪 + 人工精修"（需求池里的 P0）。

这个仓库里是一条**真的能跑的最小流水线**，加一个展示结果的网页：

选题 → 写脚本（AI 初稿 + 规则审核）→ 读 Skill → 配音 → 分段 → 素材召回 → 国家/平台规则检查 → 生成剪映草稿 → 自动评分

## 哪些是真的，哪些是简化的

| 环节 | 现在怎么做 | 真实落地换成 |
|---|---|---|
| 选题 | 按公式给选题池打分；历史爆款率是**示例数据** | 接 BI 的真实播放数据 |
| 写脚本 | 3 版初稿由 Claude 按 `data/script_prompt.md` 生成后存档；流水线按规则和事实库审核并选一版 | 脚本 Agent 实时调用大模型生成 |
| 配音 | macOS 系统语音 `say`（Daniel 英式男声），真实音频 | ElevenLabs 等配音接口 |
| 素材库 | 16 段 Pexels 实拍，标签由人工看画面标注 | 多模态模型自动打标 |
| 素材召回 | 关键词匹配（`LEXICON`）+ 地点冲突排除 | 向量检索 |
| 规则检查 | `data/rules.json` 里 6 条英国 × TikTok 规则 | 合规专员维护的规则库，RAG 检索 |
| 剪映草稿 | 用开源库 pyJianYingDraft 生成**真的剪映草稿**，剪映能直接打开 | 同左 |
| 评分 | 100 分评分标准的自动可算部分；画面节奏等需人工复核 | 加多模态模型抽帧打分 |

## 文件

- `pipeline.py`：流水线主程序
- `build_web.py`：把流水线输出整理成网页（生成 `index.html`、`audio/`、`draft/`）
- `data/`：`topics.json` 选题池、`script_prompt.md` 脚本提示词、`script_candidates.json` 3 版脚本初稿、`facts.json` 事实库、`skill.json` 剪辑规则、`rules.json` 国家/平台规则、`library.json` 素材标签、`script.json` 国家和平台
- `web/template.html`：网页模板（深色剪辑台风格，颜色都用 `:root` 里的 CSS 变量）
- `clips/m01.mp4` ~ `m16.mp4`：素材库；`thumbs/`：缩略图
- `index.html`、`audio/`、`draft/`：构建产物，发布到 GitHub Pages

## 怎么跑（需要 macOS，因为配音用了系统自带的 say 和 afconvert）

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python pipeline.py        # 默认把剪映草稿写进本机剪映草稿目录
python3 build_web.py                # 重新生成网页
```

- 剪映草稿默认写到 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/AI粗剪_伦敦苏格兰卧铺_v1`，草稿文件名是 `draft_info.json`（剪映 6.0 以后和 Mac 版 11.x 只认这个名字，库默认写的 `draft_content.json` 会被当成损坏草稿，所以 `pipeline.py` 保存后会改名；明文写入，剪映第一次打开后会自己加密）。用到的视频和配音会复制进草稿的 `materials/` 文件夹。没装剪映时用 `--draft-root <任意文件夹>`。
- 打开剪映专业版，在草稿列表里点开就能看到四条轨道：画面、配音、字幕、花字。
- 网页里加 `#topic`、`#script`、`#done-<秒>` 可以直接打开选题卡、脚本审核或生成后的某一时刻（截图用）。

## 约定

- 界面文字用简体中文；视频里的字幕和花字用英文（目标观众在英国）
- 不要引入前端框架或构建工具；网页保持单文件
- 新增素材放进 `clips/` 并在 `data/library.json` 补标签；只用可商用素材，网页底部注明出处
- 脚本里的事实必须能在 `data/facts.json` 找到出处
- 改完先跑 `pipeline.py` 和 `build_web.py`，再在浏览器里点一遍「生成粗剪」，确认视频、配音、评分、弹窗都正常

## 发布

推送到 `main` 分支后，GitHub Pages 约 1 分钟自动更新：https://ethan17461.github.io/ai-roughcut-demo/
