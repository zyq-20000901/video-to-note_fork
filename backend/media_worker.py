"""媒体阻塞调用的共享执行器。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar


T = TypeVar("T")

# 媒体下载、解码和转写必须在同一条物理工作线程上串行执行。
_MEDIA_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media-worker")


async def run_media_call(
    function: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """在共享媒体线程中运行阻塞函数。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _MEDIA_EXECUTOR, partial(function, *args, **kwargs)
    )
