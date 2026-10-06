# GPU效率与故障处理

## 保持提取质量

本机配置见`.state/gpu_ocr.json`、scripts/CX_ocr_engine.py；实际设备见`.state/ocr_device.json`。不偷偷换模型、降分辨率、跳帧、省略原文。ASR本次CPU；GPU加速OCR，27B本地分类并行，不声称ASR已上GPU。

基线：PP-OCRv6现有模型、每秒抽帧、原分辨率、FP32、TF32关闭；ONNX intra_op=4/inter_op=1。独立`.state/gpu_runtime`中的onnxruntime-gpu 1.30.0与CUDA13/cuDNN9配套库优先于首次ORT/RapidOCR导入，调用preload_dlls。三个OCR模型都以CUDAExecutionProvider为首provider才算启用，不能只看装了GPU包。

共享显存参数：enabled=true、gpu_mem_limit=1073741824、arena_shrinkage=true、classification_gpu_layers=30；Ollama请求num_gpu=30。属于RTX4070SUPER与当前27B本机基线，不是别的GPU/模型通用最优值。保留现有配置；换机/模型按显存和实测调整。

ONNX另有arena_extend_strategy=kSameAsRequested、HEURISTIC卷积搜索、禁用max_workspace。关键是在每次session推理的RunOptions加入`memory.enable_memory_arena_shrinkage=gpu:0`，释放动态形状空闲显存块。只增加池上限不能解决长队列碎片。当前代码强制shrinkage，不把配置字段单独改false后误报已停用。

逐帧visual/ocr_checkpoint.jsonl可续读；须同媒体、抽帧间隔、尺寸、模型和预处理。更换参数另建断点命名/指纹，不能复用旧结果。损坏尾行先备份，仅修复尾部，不重做完整视频。

## 健康与速度

结合frames/inference_seconds/last_frame/pid/device、GPU余显存、产物时间、两日志末尾和CPU活动。CPU ASR或分类期间OCR设备文件可不更新，不能据此重启。

CPU/GPU比较须同帧、模型、精度、尺寸与分类负载，保存文字一致性。12帧约6.10倍是小样本；GPU与27B并行600帧234.856秒也不保证整批时间。速度用时间差/帧差，不用累计耗时混算分类量。

## 按证据恢复

先定位网络/IO/格式/语音/OCR/GPU/分类哪一环；复杂新故障用systematic-debugging。不要盲重试。

| 证据 | 操作 |
|---|---|
| items瞬时空/解析失败且worker在写 | 短暂重读数次；不覆盖空列表 |
| HTTP401/403/429/503、验证页/验证码 | 对应网络队列暂停；已有素材本地继续，说明需要本人验证 |
| 有确切CDN到期时间且过期，授权作品正常页可用 | 正常页取匹配ID元数据，备份旧记录，检查新地址有效再恢复；只解释已证实的到期格式 |
| 未知403/正常页也限制 | 不推断封禁，不批量刷新试探；停止网络 |
| Chrome超时 | 核对Chrome、本机调试、允许提示；已有授权仅点该提示，不绕登录/验证码，连接恢复才续跑 |
| 媒体格式误判 | Content-Type、文件头、媒体类型、本机解码交叉核对，修正格式分支 |
| aweme_type163、audio/mpeg、ID3/MP3头 | MP3+封面，首秒本机解码；ASR音频、OCR封面 |
| aweme_type163、audio/mp4、M4A ftyp头 | M4A+封面，不作MP4视频，ocr_source_kind=audio_cover，非逐帧OCR |
| 空间不足/路径越界/缺文件 | 保留产物，解决空间/合法路径/一致性；不删原稿腾空间或计已保存 |
| provider/DLL错误 | 查导入顺序、配套库和provider；不覆盖运行中环境，识别空闲再加载 |
| BFCArena/CUDA/cuDNN分配错误 | 看ocr_gpu_error.json完整异常和故障帧；查池、动态形状碎片、shrinkage、分类显存，不反复盲加池 |
| 已回退CPU | 同模型CPU一次保住本地进度并记录；主动修复GPU，原故障长视频与正式队列确认通过后才称GPU恢复 |
| 分类失败/耗时长 | 查已安装模型、本机endpoint、显存/CPU活动和完整错误；有活动不重启，原卡保留、不静默换模型 |

GPU error可能旧记录，比较time/device时间、frames增长、PID。初始化失败可能只写device与日志，不能因error没新增忽视CPU fallback。

修代码先CX备份；健康worker不覆盖配置/重复启动。需要加载修复时安排识别安全退出或空闲，确认同类有效worker退出和锁释放，再续跑同提交；保留健康素材队列、断点与成功稿件。本地回归不等于网络重试。
