# 并行处理优化与 GPU 加速方案

## 当前状态分析

### 1. 并发控制现状
- **MAX_CONCURRENT_SUMMARIES**: 默认 3（LLM 生成笔记并发数）
- **MAX_CONCURRENT_TASKS**: 默认 3（总任务并发数）
- 使用 `asyncio.Semaphore` 进行并发控制
- 批量处理使用 `task_slots` 信号量限制并发

### 2. 当前瓶颈
1. **语音识别瓶颈**：faster-whisper 在 CPU 上处理 8 分钟音频需要约 3 分钟
2. **LLM 生成瓶颈**：依赖外部 API（OpenAI/DeepSeek），受网络和 API 限制
3. **并发限制**：固定并发数无法根据硬件动态调整

## 优化方案

### 方案 1：提高并发数（短期优化）

**改进点**：
- 将 `MAX_CONCURRENT_TASKS` 提高到 5-8（根据 CPU 核心数）
- 将 `MAX_CONCURRENT_SUMMARIES` 提高到 5（LLM API 调用不占用本地资源）
- 添加环境变量配置，允许用户根据硬件自定义

**实现**：
```python
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "5"))
MAX_CONCURRENT_SUMMARIES = int(os.getenv("MAX_CONCURRENT_SUMMARIES", "5"))
```

**预期效果**：批量处理速度提升 30-50%

### 方案 2：AMD GPU 加速支持（中期优化）

**技术路线**：
当前 `faster-whisper` 基于 CTranslate2，**仅支持 NVIDIA CUDA**，不支持 AMD ROCm。

#### 可选方案：

**A. 使用 Whisper ONNX + DirectML（推荐）**
- DirectML 支持 AMD、Intel、NVIDIA 所有 GPU
- 使用 `onnxruntime-directml` 替代 CUDA
- Windows 原生支持，无需额外驱动

**依赖**：
```
onnxruntime-directml>=1.19
```

**B. 使用 PyTorch + ROCm（仅 Linux）**
- PyTorch 2.0+ 支持 AMD ROCm
- 需要安装 ROCm 驱动（仅 Linux）
- Windows 不支持

**C. 混合方案（最佳兼容性）**
- 保留 faster-whisper（NVIDIA CUDA）
- 添加 ONNX + DirectML（AMD/Intel）
- 自动检测 GPU 类型并选择引擎

### 方案 3：并行处理架构优化（长期优化）

**改进点**：
1. **任务队列优化**：按视频时长和任务类型智能调度
2. **流式处理**：边下载边转写边生成笔记
3. **缓存优化**：LLM 提示词缓存、模型预加载

## AMD GPU 加速详细实现

### 步骤 1：检测 GPU 类型

```python
def detect_gpu_type() -> str:
    """检测 GPU 类型：nvidia、amd、intel、none"""
    if torch.cuda.is_available():
        return "nvidia"
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "DmlExecutionProvider" in providers:
            return "amd_or_intel"  # DirectML 支持两者
    except ImportError:
        pass
    return "none"
```

### 步骤 2：实现 ONNX Whisper 转写器

```python
class ONNXWhisperTranscriber:
    """使用 ONNX Runtime + DirectML 的 Whisper 转写器（支持 AMD GPU）"""
    
    def __init__(self):
        import onnxruntime as ort
        self.providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
        # DirectML 会自动选择最快的 GPU（AMD/Intel/NVIDIA）
    
    async def transcribe(self, media_path: Path, model_name: str = "base") -> dict:
        # 实现 ONNX 模型推理
        pass
```

### 步骤 3：智能引擎选择

```python
async def run_transcription(
    media_path: Path,
    model_name: str,
    use_gpu: bool = False,
) -> dict:
    """智能选择转写引擎"""
    if use_gpu:
        gpu_type = detect_gpu_type()
        if gpu_type == "nvidia":
            # 使用 faster-whisper (CTranslate2 + CUDA)
            return await whisper_transcriber.transcribe(...)
        elif gpu_type == "amd_or_intel":
            # 使用 ONNX + DirectML
            return await onnx_transcriber.transcribe(...)
    
    # 默认 CPU 路径
    return await whisper_transcriber.transcribe(...)
```

## 性能预期

| 场景 | 当前速度 | 优化后速度 | 提升 |
|------|---------|-----------|------|
| CPU 批量处理（3 任务） | 基准 | +30-50% | 提高并发数 |
| NVIDIA GPU | +300% | +300% | 已支持 |
| AMD GPU（新增） | 不支持 | +150-250% | DirectML 加速 |

## 实施建议

### 短期（1-2 天）：
1. ✅ 修复并发控制 bug（已完成）
2. 提高默认并发数
3. 添加环境变量配置

### 中期（3-5 天）：
1. 实现 ONNX + DirectML 引擎
2. 添加 GPU 类型检测
3. 实现智能引擎选择

### 长期（1-2 周）：
1. 流式处理架构
2. 任务队列优化
3. 性能监控面板

## 风险评估

1. **ONNX 模型兼容性**：需要测试 ONNX Whisper 模型质量是否与 faster-whisper 相当
2. **DirectML 稳定性**：Windows 11+ 稳定，Windows 10 需要更新
3. **维护成本**：多引擎支持增加代码复杂度

## 结论

**推荐方案**：
1. 先实施短期优化（提高并发数）- 立即见效，无风险
2. 再实施 AMD GPU 支持（ONNX + DirectML）- 性价比高，兼容性好
3. 长期持续优化架构 - 按需迭代

---
生成时间：2026-09-14
