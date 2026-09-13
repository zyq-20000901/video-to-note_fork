# 并行处理优化与 GPU 加速方案

## 当前实现分析

### 现状
- **并发模型**：使用 `asyncio.Semaphore` 限制同时处理的任务数
- **默认并发数**：5 个任务（可通过环境变量 `MAX_CONCURRENT_TASKS` 调整）
- **队列管理**：`asyncio.Queue` 管理待处理任务
- **主要瓶颈**：
  - Whisper 模型推理占用大量 CPU
  - 每个任务独立加载模型（内存开销大）
  - I/O 操作（视频下载、音频提取）与 CPU 推理混合

## 短期优化（已实施）

### 1. 提高并发数
```python
MAX_CONCURRENT_TASKS = 5  # 从 3 提升到 5
```

**效果预估**：
- 4 核 CPU：性能提升 20-30%
- 8 核 CPU：性能提升 40-60%
- 16 核 CPU：性能提升 60-80%

**限制因素**：
- 内存占用（每个模型实例约 1-3GB）
- CPU 核心数
- 磁盘 I/O 性能

## 中期优化方案

### 1. 动态并发调整

根据系统资源自动调整并发数：

```python
import psutil
import os

def calculate_optimal_concurrency():
    """根据系统资源计算最优并发数"""
    cpu_count = os.cpu_count() or 4
    available_memory_gb = psutil.virtual_memory().available / (1024**3)
    
    # 每个任务预估需要 2GB 内存
    memory_limit = int(available_memory_gb / 2)
    
    # CPU 限制：每个任务需要 1-2 个核心
    cpu_limit = max(1, cpu_count // 2)
    
    return min(memory_limit, cpu_limit, 10)  # 最多 10 个并发

MAX_CONCURRENT_TASKS = calculate_optimal_concurrency()
```

### 2. 任务优先级队列

```python
import heapq
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class PrioritizedTask:
    priority: int
    task_id: str = field(compare=False)
    data: Any = field(compare=False)

class PriorityTaskQueue:
    def __init__(self):
        self._queue = []
        self._index = 0
    
    async def put(self, priority: int, task_id: str, data: Any):
        heapq.heappush(
            self._queue,
            PrioritizedTask(priority, task_id, data)
        )
    
    async def get(self):
        if self._queue:
            return heapq.heappop(self._queue)
        return None
```

**优先级规则**：
- 小文件优先（快速完成，提升用户体验）
- 用户手动触发的任务优先
- 失败重试任务降低优先级

### 3. 模型池化

```python
from typing import Dict
import asyncio

class WhisperModelPool:
    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.models = asyncio.Queue(maxsize=pool_size)
        self._initialized = False
    
    async def initialize(self):
        """预加载模型到池中"""
        if self._initialized:
            return
        
        for _ in range(self.pool_size):
            model = await asyncio.to_thread(
                lambda: WhisperModel(
                    model_size_or_path="base",
                    device="cpu",
                    compute_type="int8"
                )
            )
            await self.models.put(model)
        self._initialized = True
    
    async def acquire(self):
        """获取一个模型实例"""
        return await self.models.get()
    
    async def release(self, model):
        """归还模型实例到池中"""
        await self.models.put(model)

# 全局模型池
model_pool = WhisperModelPool(pool_size=3)

async def process_with_pool(audio_file: str):
    model = await model_pool.acquire()
    try:
        result = await asyncio.to_thread(
            model.transcribe,
            audio_file
        )
        return result
    finally:
        await model_pool.release(model)
```

**优势**：
- 避免重复加载模型（节省时间和内存）
- 更好的资源利用率
- 支持模型预热

### 4. 分离 I/O 和计算

```python
async def process_video_pipeline(video_path: str):
    """将 I/O 和计算分离，提高并行效率"""
    
    # 阶段 1：I/O 密集（快速完成）
    async with io_semaphore:  # 允许更多并发
        audio_path = await download_and_extract_audio(video_path)
    
    # 阶段 2：CPU 密集（限制并发）
    async with compute_semaphore:  # 限制 CPU 任务数量
        transcription = await transcribe_audio(audio_path)
    
    # 阶段 3：I/O 密集
    async with io_semaphore:
        result = await save_results(transcription)
    
    return result

# 不同类型任务使用不同的并发限制
io_semaphore = asyncio.Semaphore(10)  # I/O 可以高并发
compute_semaphore = asyncio.Semaphore(5)  # CPU 任务受限
```

## GPU 加速方案

### 当前技术栈分析

项目使用 **faster-whisper**（基于 CTranslate2）：
- 优点：比原生 Whisper 快 4-5 倍，内存占用低
- 缺点：主要优化 NVIDIA CUDA，AMD 支持有限

### AMD GPU 加速可行性

#### 方案 1：ROCm + faster-whisper（推荐 Linux）

**适用场景**：Linux + AMD Radeon RX 系列 / Instinct 系列

**要求**：
- AMD GPU（支持 ROCm）
- Linux 系统（Ubuntu 20.04/22.04）
- ROCm 5.0+

**安装步骤**：
```bash
# 安装 ROCm
wget https://repo.radeon.com/amdgpu-install/latest/ubuntu/jammy/amdgpu-install_latest_all.deb
sudo dpkg -i amdgpu-install_latest_all.deb
sudo amdgpu-install --usecase=rocm

# 安装 PyTorch for ROCm
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7

# 编译支持 ROCm 的 CTranslate2（可能需要从源码编译）
```

**挑战**：
- ROCm 生态不如 CUDA 成熟
- 可能需要从源码编译 CTranslate2
- 兼容性问题较多

**预期提升**：3-5 倍（相比 CPU）

#### 方案 2：ONNX Runtime + DirectML（推荐 Windows）

**适用场景**：Windows + 任意 AMD/Intel/NVIDIA GPU

**优点**：
- 跨平台跨硬件
- DirectML 支持所有 DX12 兼容 GPU
- 安装简单

**实现**：
```python
# 安装依赖
# pip install onnxruntime-directml

import onnxruntime as ort

# 使用 DirectML 执行提供程序
providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
session = ort.InferenceSession(model_path, providers=providers)

# 需要将 Whisper 模型转换为 ONNX 格式
# 可以使用 optimum 库：
# pip install optimum[onnxruntime]
# optimum-cli export onnx --model openai/whisper-base whisper-onnx/
```

**挑战**：
- 需要将 Whisper 转换为 ONNX 格式
- 可能需要修改推理代码
- 性能可能不如原生 CUDA

**预期提升**：2-3 倍（相比 CPU）

#### 方案 3：OpenVINO（推荐 Intel 设备）

**适用场景**：Intel CPU/GPU/VPU

**优点**：
- Intel 官方支持
- 优化非常好
- 部署简单

**实现**：
```bash
pip install openvino-dev

# 转换模型
mo --saved_model_dir whisper_model --output_dir whisper_openvino
```

**限制**：主要优化 Intel 设备，AMD GPU 支持有限

#### 方案 4：原生 Whisper + PyTorch ROCm

**最稳妥的方案**：
```python
# 安装 PyTorch for ROCm
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7

# 使用原生 Whisper
import whisper

model = whisper.load_model("base")
model = model.to("cuda")  # ROCm 的 PyTorch 也使用 "cuda"

result = model.transcribe("audio.mp3")
```

**缺点**：比 faster-whisper 慢，但支持 ROCm

**预期提升**：2-4 倍（相比 CPU）

### 推荐方案对比

| 方案 | 平台 | 难度 | 性能 | 稳定性 |
|------|------|------|------|--------|
| ROCm + faster-whisper | Linux | 高 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| ONNX + DirectML | Windows | 中 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| OpenVINO | Intel | 低 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Whisper + PyTorch ROCm | Linux | 中 | ⭐⭐⭐ | ⭐⭐⭐⭐ |

### 实施建议

#### 第一阶段（验证可行性）
1. 在测试环境安装 PyTorch ROCm
2. 使用原生 Whisper 测试 AMD GPU 是否工作
3. 对比 CPU vs GPU 的实际性能提升

#### 第二阶段（性能优化）
- 如果 ROCm 工作良好：尝试编译 CTranslate2 with ROCm
- 如果 ROCm 问题多：改用 ONNX + DirectML

#### 第三阶段（生产部署）
- 提供 CPU 和 GPU 两种部署选项
- 自动检测硬件并选择最优后端
- 添加性能监控和对比

## 监控和诊断

### 性能指标

```python
import time
import psutil
from dataclasses import dataclass

@dataclass
class TaskMetrics:
    task_id: str
    start_time: float
    end_time: float
    cpu_percent: float
    memory_mb: float
    gpu_utilization: float = 0.0
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

class PerformanceMonitor:
    def __init__(self):
        self.metrics = []
    
    async def track_task(self, task_id: str, coro):
        """跟踪任务性能"""
        process = psutil.Process()
        start_mem = process.memory_info().rss / 1024 / 1024
        start_time = time.time()
        
        result = await coro
        
        end_time = time.time()
        end_mem = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent()
        
        self.metrics.append(TaskMetrics(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
            cpu_percent=cpu_percent,
            memory_mb=end_mem - start_mem
        ))
        
        return result
    
    def get_stats(self):
        """获取统计信息"""
        if not self.metrics:
            return {}
        
        durations = [m.duration for m in self.metrics]
        return {
            "total_tasks": len(self.metrics),
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "total_time": sum(durations)
        }
```

### 实时监控接口

```python
@router.get("/batch/performance")
async def get_performance_stats():
    """获取性能统计信息"""
    return {
        "queue_size": task_queue.qsize(),
        "active_tasks": MAX_CONCURRENT_TASKS - task_slots._value,
        "completed_tasks": len(monitor.metrics),
        "stats": monitor.get_stats(),
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "available_memory_gb": psutil.virtual_memory().available / 1024**3
        }
    }
```

## 测试计划

### 性能基准测试

```bash
# 测试不同并发数的性能
for concurrent in 1 3 5 8 10; do
    export MAX_CONCURRENT_TASKS=$concurrent
    python benchmark.py --videos 20 --output results_${concurrent}.json
done
```

### 对比测试
1. CPU vs GPU（如果 GPU 可用）
2. 不同模型大小（tiny/base/small）
3. 不同并发数（1/3/5/8/10）
4. 不同视频长度（短/中/长）

## 实施优先级

### P0（立即实施）
- ✅ 提高默认并发数到 5
- ✅ 添加环境变量配置

### P1（1-2 周）
- 动态并发调整
- 任务优先级队列
- 性能监控接口

### P2（1 个月）
- 模型池化
- I/O 和计算分离
- AMD GPU 加速验证

### P3（长期）
- 分布式处理（多机协作）
- 增量模型更新
- 智能缓存策略

## 风险和注意事项

1. **内存溢出**：并发数过高可能导致 OOM
2. **GPU 兼容性**：AMD GPU 支持不如 NVIDIA 成熟
3. **部署复杂度**：GPU 加速会增加安装难度
4. **成本收益**：需要评估性能提升是否值得增加的复杂度

## 参考资料

- [faster-whisper GitHub](https://github.com/guillaumekln/faster-whisper)
- [ROCm Documentation](https://rocmdocs.amd.com/)
- [ONNX Runtime DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [OpenVINO Toolkit](https://docs.openvino.ai/)
- [CTranslate2 Documentation](https://opennmt.net/CTranslate2/)
