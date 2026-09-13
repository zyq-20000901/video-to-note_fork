# Repository Guidelines

## 项目结构

`backend/` 是 FastAPI 服务：`main.py` 提供 HTTP/MCP 接口，`video_processor.py`、`whisper_asr.py`、`llm_summarizer.py` 分别处理媒体、转写和摘要。`frontend/` 是无构建步骤的原生 HTML/CSS/JavaScript；`frontend/vendor/` 为锁定的第三方浏览器资源，除升级依赖外不要手改。`tests/` 放 pytest 测试，`launcher.py` 负责开发与便携版启动，`scripts/` 包含图标和 Windows 打包脚本，`skills/video-to-note/` 是随仓库发布的 Agent Skill。

## 本地开发与构建

项目目标环境为 Windows 和 Python 3.11。在仓库根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\start.ps1 -Foreground
.\stop.ps1
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

`start.ps1` 默认仅绑定 `127.0.0.1:8000`；`-Foreground` 便于观察启动日志。打包命令生成 Windows 便携版，勿提交 `build/`、`dist/` 或生成的版本元数据。

## 代码与测试规范

Python 使用四空格缩进、类型标注、`snake_case` 函数/变量、`PascalCase` 类和全大写模块常量；保持邻近模块的导入顺序和中文用户提示风格。前端继续使用原生 JavaScript，不引入打包器、框架或未配置的格式化工具。新增行为应补充 `tests/test_<主题>.py` 中的 `test_<行为>()`；异步测试标记 `@pytest.mark.asyncio`，通过 `tmp_path` 与 `monkeypatch` 隔离文件、网络、GPU 和外部服务。

## 提交、PR 与安全

提交历史采用 Conventional Commits，例如 `feat(ui): ...`、`fix(api): ...`、`docs(skill): ...`、`chore: ...`。每次提交只包含一个可验证变更。PR 说明应写清行为影响、运行过的测试和配置变化；修改界面时附截图。不要提交 `.env`、`workspace/`、运行日志、API Key、Cookie 或构建产物。服务设计为本机优先，未经明确需求不得把监听地址改为公网可访问。
