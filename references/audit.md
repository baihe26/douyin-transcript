# 计数与验收

`scripts/audit_task.py`仅Python标准库。指定任务，只读元数据与产物统计；不读全文分析，不启动/结束worker，不联网。

```powershell
& '<本机Python>' '<skill目录>\scripts\audit_task.py' --root '<工具根>' --job '<任务名>' --submission '<提交编号>' --processes
# 需保存记录才加 --write-monitor；不等于创建定时任务
```

默认输出简短JSON。--write-monitor原子写对应提交monitor_latest.json并追加monitor_history.jsonl；同job/submission/counter_schema才比较增长。首次换计数口径不沿用差值。新任务不使用写死旧提交的CX_monitor_local.py。

| 指标 | 实际口径 |
|---|---|
| 范围 | 当前manifest去重作品数，不固定740；分页完整与来源数量差异另报 |
| 素材 | 登记有效媒体作品ID ∪ 有效completed作品ID；files存在非空、在该job内，封面不另计 |
| 语音稿文件 | transcript.txt存在；图文无语音占位与实际ASR分别记 |
| OCR处理 | 状态完成且screen_text.txt存在；无文字单独列信息不足 |
| 完整提取 | 逐条终态+有效媒体+适用语音稿+适用OCR；仅任务no-ocr时允许跳过 |
| 本地分类 | 所有analysis.status=complete且有整理卡，按作品去重 |
| 助手归纳/Word | 单独核对分类清单、文档ID和归纳深度，不用本地classified替代 |

不以baseline_saved+全量completed算素材，baseline可能已含合并新增；不以游标/提交数/帧数算完整提取。

检查status.mode/result.stage/local_error、media.state/stage/error。只读analysis.status做统计，不展示summary；items瞬时失败重读。进程按脚本名+submission、父子树去重；锁文件存在不等于锁被占用。状态时间旧须结合日志、产物与CPU活动；进程信息不可读时说明缺失。

非空文件不证明媒体完整或可解码，必要格式和首秒解码由下载器/本地检查负责。已下载未登记的孤立文件不凭名字算完成，先修元数据。语音/OCR无字结合原响应判断无内容或识别失败。

验收manifest、items、语音/segments、OCR原行/screen_text、媒体、整理卡和reports/organize_status.json。分别报告提取成功/失败/未处理/unsupported、分类成败与来源差异。监督仅用户要求才按频率汇报增长和异常；仅保存素材不是全部完成。

Word验收全部授权ID与主文档ID一致，每条一个主归属，索引/交叉引用可重复；所有文档非空、ZIP/OOXML有效、全文语音与附件一致。有渲染能力再查中文布局；只做结构检查不声称视觉验收。
