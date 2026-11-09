# AI 粗剪工作台

出海火车票短视频业务的 AI 粗剪最小流水线：选题 → 写脚本（AI 初稿 + 规则审核）→ 配音 → 素材召回 → 国家/平台规则检查 → **生成真的剪映草稿** → 自动评分 → 人工精修。

在线查看结果：https://ethan17461.github.io/ai-roughcut-demo/

素材来自 Pexels（免费可商用）；选题的历史数据为示例数据；剪映草稿由开源库 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) 生成。

## 在自己电脑上继续改

```bash
git clone https://github.com/ethan17461/ai-roughcut-demo.git
cd ai-roughcut-demo
```

怎么跑、哪些是真的哪些是简化的，都写在 `AGENTS.md`，用 Codex 编辑时它会先读这份说明。要把修改推回这个仓库，需要仓库主人在 Settings → Collaborators 里把你加为协作者。
