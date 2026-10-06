# 依赖来源与复用记录

本仓库的通用操作说明、环境助手与审计脚本来源于本地流程的整理及本次新增实现；没有复制外部仓库实现代码，没有捆绑模型、软件安装包或第三方源码。以下项目只通过其公开Python/命令接口使用，安装到使用者本机；下载前按官方说明检查兼容性与各自许可证。

| 项目 | 官方来源 | 用途 |
|---|---|---|
| FunASR / SenseVoice | https://github.com/modelscope/FunASR / https://github.com/FunAudioLLM/SenseVoice | 本地语音与VAD |
| RapidOCR | https://github.com/RapidAI/RapidOCR | 本地画面识别 |
| ONNX Runtime | https://onnxruntime.ai/docs/install/ | CPU/GPU推理及CUDA配套说明 |
| imageio-ffmpeg | https://pypi.org/project/imageio-ffmpeg/ | 可复用的本地FFmpeg二进制 |
| PyTorch | https://pytorch.org/get-started/locally/ | CPU语音底座 |
| Playwright | https://playwright.dev/python/docs/intro | 隔离浏览器基础 |
| python-docx | https://python-docx.readthedocs.io/ | Word输出 |
| Ollama | https://ollama.com/download | 可选本地自动分类 |

环境检查时间：2026-10-06。依赖范围用于兼容选择，不代表未来版本均通过测试；安装实际版本另存本机installed-versions.txt。已有锁定环境优先复用，硬件参数不是通用最优值。
