import os
import psutil


def get_process_memory_usage():
    # 获取当前进程的 PID
    pid = os.getpid()

    # 使用 psutil 获取当前进程
    process = psutil.Process(pid)

    # 获取内存使用信息（单位为字节）
    memory_info = process.memory_info()

    # 转换为 MB（可根据需要选择不同的单位）
    memory_usage_mb = memory_info.rss / 1024 / 1024

    return memory_usage_mb


if __name__ == "__main__":
    memory_usage = get_process_memory_usage()
    print(f"当前进程的内存占用：{memory_usage:.2f} MB")