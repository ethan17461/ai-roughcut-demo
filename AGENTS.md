# AGENTS.md

给 Codex 等 AI 编程助手看的项目说明。改代码前先读这一页。

## 项目是什么

AI 产品经理课程的模拟项目：给一家做出海火车票短视频引流的业务方，做"AI 粗剪 + 人工精修"（需求池里的 P0）。

这个仓库里是一条**真的能跑的流水线**，加两个网页：

选题 → 写脚本（DeepSeek 写 3 版 + 规则审核）→ 读 Skill → 配音（MiniMax）→ 分段 → 素材召回 → 国家/平台规则检查 → 生成剪映草稿 → 自动评分 → 人工换镜头、写回剪映

- **本地工作台**（`studio.py`）：在浏览器里输入选题，现场跑完整流程，逐句检查画面、换镜头、写回剪映草稿。需要 API key，只在本机跑。
- **在线展示页**（`index.html`，GitHub Pages）：回放某一次真实运行的结果，不调接口。

## 哪些是真的，哪些是简化的

| 环节 | 现在怎么做 | 真实落地换成 |
|---|---|---|
| 选题 | 输入选题时直接用；不输入时按公式给选题池打分（历史爆款率是**示例数据**） | 接 BI 的真实播放数据 |
| 写脚本 | DeepSeek（deepseek-chat）按 `data/script_prompt.md` 现写 3 版，每句同时标出要什么画面、说到哪个地点；流水线按规则和事实库审核，具体时刻/价格标"需人工核对" | 同左，事实库由运营维护 |
| 配音 | MiniMax 语音合成（speech-2.8-hd，英式女声 English_Graceful_Lady）；没 key 或余额不足时整条退回 macOS 系统语音 | 同左 |
| 素材库 | 53 段 Pexels 实拍（火车、车窗、车站、7 座城市、阿尔卑斯、湖、海岸、乡村、电子票），标签和"能代表哪些地点"由人工看画面标注 | 公司自己的素材库 + 多模态模型自动打标 |
| 素材召回 | 按 DeepSeek 给的画面概念加权匹配标签，地点对不上的排除，地点对得上的加分；每个概念至少给一个候选 | 向量检索 |
| 规则检查 | `data/rules.json` 里 6 条英国 × TikTok 规则 | 合规专员维护的规则库，RAG 检索 |
| 剪映草稿 | 开源库 pyJianYingDraft 生成**真的剪映草稿**，剪映能直接打开 | 同左 |
| 评分 | 100 分评分标准的自动可算部分；画面节奏等需人工复核 | 加多模态模型抽帧打分 |

## 文件

- `pipeline.py`：流水线主程序（`--topic` 现场生成；不带参数跑存档示例；`--redraft` 按人工换过的镜头重写草稿）
- `llm.py`：DeepSeek / MiniMax 接口（只用标准库）
- `studio.py`：本地工作台服务器（http://localhost:8770）
- `build_web.py`：把最近一次运行整理成在线展示页（生成 `index.html`、`audio/`、`draft/`）
- `data/`：`topics.json` 选题池、`script_prompt.md` 脚本提示词、`script_candidates.json` 存档的 3 版脚本、`facts.json` 事实库、`skill.json` 剪辑规则和配音音色、`rules.json` 国家/平台规则、`library.json` 素材标签、`script.json` 国家和平台
- `web/template.html`：两个网页共用的模板（深色剪辑台风格，颜色都用 `:root` 里的 CSS 变量；`STUDIO` 为 true 时显示输入框和"写入剪映"）
- `clips/m01.mp4` ~ `m53.mp4`：素材库；`thumbs/`：缩略图
- `.env`：API key（不进 git），格式见 `.env.example`

## 怎么跑（需要 macOS：音频转换用了系统自带的 afconvert，兜底配音用 say）

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # 填 DEEPSEEK_API_KEY、MINIMAX_API_KEY
.venv/bin/python studio.py         # 打开 http://localhost:8770 ，输入选题点「生成粗剪」
```

命令行也能跑：

```bash
.venv/bin/python pipeline.py --topic "从巴黎坐火车去阿姆斯特丹，周末两日游"
.venv/bin/python pipeline.py       # 存档示例，不需要 key
python3 build_web.py               # 用最近一次运行重新生成在线展示页
```

- 剪映草稿默认写到 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/`。现场生成的草稿名是"AI粗剪_选题前几个字_月日-时分"，每次新建一个；存档示例固定叫 `AI粗剪_伦敦苏格兰卧铺_v1`。没装剪映时用 `--draft-root <任意文件夹>`。
- 草稿文件名必须是 `draft_info.json`（剪映 6.0 以后和 Mac 版 11.x 只认这个名字，库默认写的 `draft_content.json` 会被当成损坏草稿，所以保存后会改名；明文写入，剪映第一次打开后会自己加密）。用到的视频和配音会复制进草稿的 `materials/` 文件夹。
- 剪映开着的时候新生成的草稿可能不出现在列表里，退出剪映（⌘Q）再打开即可。
- 网页里加 `#topic`、`#script`、`#done-<秒>` 可以直接打开选题卡、脚本审核或生成后的某一时刻（截图用）。
- 费用参考：DeepSeek 一次约 2,500 tokens；MiniMax 一条约 300 字符（3.5 元/万字符，约 0.1 元）。

## 约定

- 界面文字用简体中文；视频里的字幕和花字用英文（目标观众在英国）
- 不要引入前端框架或构建工具；网页保持单文件
- 新增素材放进 `clips/` 并在 `data/library.json` 补标签和 `places`；只用可商用素材，网页底部注明出处
- 脚本里的事实必须能在 `data/facts.json` 找到出处，找不到的写进 claims 交人工核对；不提第三方品牌
- API key 只放 `.env`，不要写进代码、网页或提交记录
- 改完先跑一遍 studio，输入一个选题生成，再换一个镜头点「写入剪映」，确认视频、配音、评分、弹窗、剪映草稿都正常

## 发布

`python3 build_web.py` 后推送到 `main` 分支，GitHub Pages 约 1 分钟自动更新：https://ethan17461.github.io/ai-roughcut-demo/
