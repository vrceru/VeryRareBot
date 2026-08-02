import platform
import socket
import time

import psutil


BOOT_TIME = psutil.boot_time()


def hostname():
    return socket.gethostname()


def operating_system():
    return f"{platform.system()} {platform.release()}"


def python_version():
    return platform.python_version()


def cpu_usage():
    return psutil.cpu_percent(interval=1)


def memory_usage():
    return psutil.virtual_memory()


def disk_usage():
    return psutil.disk_usage("/")


def uptime():

    seconds = int(time.time() - BOOT_TIME)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    return f"{days}d {hours}h {minutes}m"
