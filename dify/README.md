# Dify 七维视频评测工作流

`team_video_review.yml` 是从已有的本机工作流导出的副本，保留了视频分析、抽帧联系表、DeepSeek 视觉模型等原有接线；评分使用七维 100 分，所有小项可评后才显示完整总分。

工作流最终只输出一份文本：包含“评分”和“安全、转人工”；有经过证据校验的修改建议时，才显示“优化建议”。

## 必须先具备的条件

这不是独立运行包：工作流请求 `http://host.docker.internal:8765/analyze` 与辅助服务返回的临时抽帧联系表。该服务在现有 macOS 项目的 `dify_video/metrics_server.py` 中，依赖相应语音识别及本机授权；Docker Desktop、Dify 的代理连通性、DeepSeek 视觉模型和服务均需要由环境管理员配置。仅分享 YAML 无法让他人直接处理视频，也不能连接到别人电脑上的 `host.docker.internal`。请勿将本机辅助服务直接暴露到公网。

在有对应服务的 Dify 中导入 YAML，选取实际视频，填写脚本和语音语言并运行。视频抽帧、脚本和转写文本会发送到配置的模型服务；Dify 可能保存上传文件和运行记录。

## 人工核验

首次可以不填写“人工核验 JSON”，工作流会列出七维各小项的编号、满分和待确认状态。抽帧只覆盖部分画面，AI 不能确认整条视频没有人脸、国旗或竞品标识，也无法可靠判断音质、字幕、完整节奏和事实。

人工看过完整视频后，可以再次运行并填写 JSON。`scores` 中每项只接受 `0`、该项的部分分或满分；`risk` 中分别填写 `found`（确认出现）、`absent`（确认未出现）、`unknown`（尚未确认）。示例：

```json
{"scores":{"opening_hook":8,"sound_clear":2},"risk":{"face":"found","flag":"absent","competitor_logo":"unknown"}}
```

`face`、`flag`、`competitor_logo` 任一人工确认为 `found`，无论分数如何直接判为不合格；全部 `absent` 仅表示这三项人工确认未出现，并不保证其他事实、版权或平台规则通过。AI 提示疑似风险仍需人工核实。人工结果由用户再次运行时提交；当前工作流没有自动保存或在输出页直接修改的功能。

## 检查

在已安装项目依赖的环境中运行 `.venv/bin/python -m unittest discover -s dify/tests -v`。测试只验证评分和规则逻辑，不能替代在目标 Dify 实际导入及上传视频测试。`report_code.py` 与 DSL 中的 report 节点须保持一致。
