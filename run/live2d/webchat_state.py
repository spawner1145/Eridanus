"""
兼容性再导出：真正的状态已移到 framework_common（稳定单例），原因见该模块文档。
保留本文件以防其它地方仍按旧路径 import；新代码请直接用 framework_common 版本。
"""

from framework_common.framework_util.live2d_webchat_state import (  # noqa: F401
    _STATE,
    get_state,
    set_runtime,
)
