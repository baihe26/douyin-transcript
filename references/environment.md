# 工作前检查与按需补齐环境

每次新机器、新任务、迁移或环境故障，先确定本轮需要哪些能力。只有分类已有文字时无需安装 ASR/OCR；只转写选 ffmpeg,asr；图文选 ocr；视频提取选 ffmpeg,asr,ocr；Word 加 word；新采集加 collect。GPU 加 gpu。助手分类无需安装本地分类模型。

## 先复用，再补齐

1. 读取工具根、任务配置、已有 doctor/setup/锁文件，定位实际 Python、FunASR 根、模型和浏览器缓存。用 `DOUYIN_TOOL_ROOT` / `DOUYIN_FUNASR_ROOT` 或命令参数选择，不把另一台电脑路径当默认事实。
2. 用 `scripts/ensure_environment.py` 检查。入口只依赖 Python 标准库。默认只读，不启动采集、不读取私人原文、不下载权重。
3. 查看每一项 status：`ready` 有对应运行证据；`detected` 仅发现包与权重；`missing` 缺包/二进制/模型；`failed` 是运行故障。缺失才安装，失败先诊断。退出码 0 表示请求的能力均 ready；2 表示仍有缺项或未核验，不能称环境全部正常。
4. 检测缺失时按任务授权执行 `--install`，只从官方 PyPI/PyTorch 来源安装所需包，在所选工作区 `.skill-runtime/<component>` 新建隔离虚拟环境。既有 `.venv`、模型、GPU配置与运行中worker保留。遇到空间不足、权限/联网失败或安装锁占用，保留产物并报告具体阻碍。
5. 缺权重时使用对应官方模型入口下载本地权重，随后运行本地合成样本核验。禁止改用云语音、云OCR。安装依赖不等于有可用模型；有权重不等于成功推理。

```powershell
# 检查已选工作区，本地推理核验；报告只存本机
python '<skill目录>\scripts\ensure_environment.py' --root '<工具根>' --components ffmpeg,asr,ocr --verify --output '<本机报告路径>.json'
# 缺什么补什么，并核验；已可用的环境不会重复安装
python '<skill目录>\scripts\ensure_environment.py' --root '<工具根>' --components ffmpeg,asr,ocr,word --install --output '<本机报告路径>.json'
```

可指定 `--tool-python`、`--asr-root`、`--asr-url`（仅HTTP回环）、`--ocr-models`、`--gpu-runtime`。ASR服务未启动但权重已存在时可以在独立子进程本地核验；正式流水线若依赖HTTP服务，必须使用原工具启动入口，确认 `/health` 的 ready=true、端口与配置匹配后才能接入。不因一次检测自动启动或重启第二个服务。

脚本输出每阶段实际 Python；新隔离环境必须通过工具配置/派生适配接入对应阶段，随后重跑工具 doctor。原工具不支持分阶段Python时，在派生副本增加配置适配，或者使用现有官方setup在确认无有效worker、保留锁定版本的环境中补装。**不能只看到探针通过，就声称原采集工具已能调用新环境。** 此技能包是流程和环境助手，不包含原采集器、私人任务库或所有媒体处理脚本。缺原工具时先定位或按用户授权准备工具，不虚构脚本存在。

## GPU要实际确认

- 查看 `nvidia-smi`、显存余量、实际 ONNX provider、模型与现有独立GPU运行库。先用既有CPU底座和独立GPU库，不在同一site-packages混装CPU/GPU的onnxruntime。
- `--components gpu --verify` 实际初始化三模型、确认首provider均为CUDA并推理合成文字；探针使用shrinkage，不写正式ocr_device.json。它只证明本次短样本推理，不能证明长队列速度、稳定性或抽帧质量。
- 缺GPU库时先核对 [ONNX Runtime安装说明](https://onnxruntime.ai/docs/install/) 和 [CUDA兼容矩阵](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)，选与当前Python、驱动、CUDA/cuDNN匹配的**官方固定版本**，再传 `--gpu-spec 'onnxruntime-gpu[cuda,cudnn]==<已核对版本>' --install`。脚本不猜CUDA版本、不自动装系统驱动、不覆盖旧GPU参数。新模型/硬件按显存调整参数，不能套用示例上限。
- 缺驱动、VC运行库、需重启或管理员权限时，明确记录待完成步骤；不用CPU成功掩盖GPU故障。恢复加载时确认有效worker退出、锁释放，按GPU恢复参考执行。

## 可用性证据与限制

| 能力 | 运行核验 | 仍需正式任务确认 |
|---|---|---|
| FFmpeg | 执行与合成音频解码 | 实际MP4/MP3/M4A解码 |
| ASR | 已加载模型健康或本地合成音频推理 | 中文真实语音准确度、正式服务接入 |
| OCR | 合成文字识别与三模型加载 | 原分辨率视频/图文完整提取 |
| GPU | 三模型CUDA首provider、实际推理 | 原故障长视频、长队列、与分类共享显存 |
| Word | 中文DOCX保存并读回 | 字体与视觉排版 |
| 采集基础 | 隔离Chromium二进制/本地页面 | 本人登录、Chrome扩展连接、授权范围分页与原采集器 |

SenseVoice/FSMN-VAD与RapidOCR默认权重由各自官方库下载到本机；自定义模型通过显式路径复用，若模型目录缺失/歧义，先核对原模型配置再安装，不更换健康模型。Ollama仅本地自动分类时需要：检查官方程序、回环endpoint、用户已选模型和显存，缺失从 [Ollama官方](https://ollama.com/download) 安装并拉取明确选定模型；不要自动选27B或别的模型。无Python时先查系统/工具/宿主自带Python，仍缺则从 [Python官方](https://www.python.org/downloads/) 安装兼容版本，再创建工作区venv。

报告与安装日志含本机路径，只留本机。发布技能仅发布通用脚本、说明、合成验证用例，排除报告、环境、模型、Cookie、签名媒体URL、原稿与个人范围。记录依赖实际版本；下次复用，禁止盲目升级修复健康环境。
