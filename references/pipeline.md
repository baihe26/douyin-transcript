# 收集、并行与断点

## 范围入口

在已核对工具根运行submit_library.cmd；返回submission、job和本地进度页。仅用户要求同步等待时用run_library.cmd；两者接受相同library参数。

| 输入 | 参数 |
|---|---|
| 分享文字/多链接 | `batch --links-file <绝对路径>` |
| 本人收藏视频及个人收藏夹 | `collect --source favorites` |
| 指定收藏夹 | `collect --source folder --folder-name <精确名称>` 或 `--folder-id <真实ID>` |
| 收藏的全部合集 | `collect --source mixes` |
| 收藏另含合集 | `collect --source favorites --include-mixes` |
| 作者 | `collect --source author --url <完整主页>` |
| 合集 | `collect --source mix --url <完整链接>` |
| 原job续跑 | `resume --job <任务名>` |
| 只分类 | `organize --job <任务名>` |
| 先收集 | collect加 `--job <新任务名> --collect-only` |
| 追加新增 | 原范围、同job加 `--refresh`，仅用户要求更新时 |

通常附--open-result；只语音加--no-ocr；自定义分类--categories-file <JSON>；模型--model指定已安装本地模型。先按environment.md检查/补齐所需环境，再运行原工具doctor；不静默用远程识别。

记录各来源分页游标、has_more、接口成功状态、归属、页面数量与实际返回数。正常末页或用户指定选择边界才算收集结束；滚动停止、空响应、验证码、数量上限不算全部。未返回/删除/不可访问单独记录，不补其他作品。

## 浏览器与兼容性

隔离浏览器需本人登录；授权已有Chrome用scripts/chrome_session.py本机调试连接，不复制个人配置。正常页面返回匹配授权ID的元数据；无关预加载响应不进清单。官方子域名用实际域名判断，不放任意主机。

20261005核对：

- library.py通用收集入口对图文可能标unsupported，不能声称已具有Chrome图文能力。
- chrome_batch_task.py、chrome_process_batch.py建任务入口写死旧作者/收藏夹、八来源、job与plan。新范围不能直接运行；用通用收集或在CX派生副本参数化范围，再建立匹配清单和私有元数据。
- CX_save_remaining_media.py按submission查job/manifest，但要求`.state/authorized_media/<job>/<aweme_id>.json`存在，媒体类型和官方域名通过校验。
- CX_process_saved_local.py按submission处理素材，但分类线程读取`<既有批次的分类配置>.json`。新任务先在派生副本改为当前分类配置；不能沿用旧分类或修改正在跑的worker。
- CX_monitor_local.py写死旧job/submission，新任务用Skill的audit_task.py。

操作流程通用不代表旧脚本均参数化。新任务适配保留旧文件与运行中实例，不让用户旧批次重跑。

## 双阶段流水线

前提：manifest固定、items范围匹配、脚本满足兼容性。媒体保存与本地识别可同提交并行；先确认实际文件再识别。网络单队列每作品至少30秒，图片间15秒，不加下载并发提速。

| 阶段 | 启动器参数 | 状态与日志 | 锁 |
|---|---|---|---|
| 媒体 | `.venv\Scripts\python.exe scripts\CX_save_remaining_media.py <submission>` | media_stage.json、media_worker.log | 提交目录media-stage.lock |
| 识别 | `.venv\Scripts\python.exe scripts\CX_process_saved_local.py <submission>` | status.json、worker.log | 根目录.state/submissions/local-worker.lock |
| 空闲合并 | `.venv\Scripts\python.exe scripts\CX_merge_saved_media.py <submission>` | media_merge.json | 同local-worker锁 |

提交目录`.state/submissions/<submission>`；任务`jobs/<job>`。启动器自动创建隐藏后台`--worker <submission>`；不手动重复启动--worker。健康时保留，不另启动旧chrome_process_batch.py网络worker。

本地worker每20条小批，优先已transcribed。音频提取/CPU ASR/GPU OCR线程独占items写入；分类线程只读OCR完成的作品并写卡片。GPU OCR在分类线程前初始化。持锁worker自行合并staged媒体，不外部合并。

媒体completed每行一作品，files必须非空、存在、非空文件、位于授权作品目录。音频合并media_kind=audio，兼容video_files只含MP3/M4A，source_cover_files独立；封面不另计。

## 退出恢复

1. 同时按命令行脚本名与submission、PID/父PID、CPU活动核对。venv父启动器与实际Python子进程是一棵worker树。锁文件存在不等于占锁，旧PID可能被其他应用复用。
2. 本地worker确已退出才合并，busy=true立即停止；merged>0或存在已保存待处理/分类待恢复才续跑本地worker。merged=0无待办不循环启动。
3. 媒体退出先看media_stage.error。平台限制保暂停；可恢复本地故障修复且同类退出后续跑原提交。staged_complete且素材全部有效不再启动媒体。
4. saved_media_only的status.network_paused只指原下载分支；不能据此判media暂停。状态更新时间旧不能单独判卡死。
