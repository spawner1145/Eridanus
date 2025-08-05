import gc
import os

import psutil
from pympler import muppy, summary

class logger:
    def __init__(self):
        pass

    def info(self, msg):
        print(msg)


logger = logger()
def get_memory_usage():
    """获取当前进程的内存使用情况"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    rss_mb = memory_info.rss / 1024 / 1024  # 物理内存
    return round(rss_mb, 2)


def analyze_objects(index=0):
    """分析内存中的对象"""
    gc.collect()  # 强制垃圾回收
    all_objects = muppy.get_objects()
    sum1 = summary.summarize(all_objects)

    logger.info(f"point: {index}  总对象数: {len(all_objects)}, 内存占用: {get_memory_usage()}MB")
    logger.info("Top 10 对象类型:")
    for i, (obj_type, count, total_size) in enumerate(sum1[:10]):
        size_mb = total_size / (1024 * 1024)
        logger.info(f"  {i + 1}. {str(obj_type):<30} 数量:{count:<8} 大小:{size_mb:.2f}MB")