import os
import platform
import ctypes


def get_free_space_mb(folder):
    """
    获取磁盘剩余空间
    :param folder: 磁盘路径 例如 D:\\
    :return: 剩余空间 单位 Byte
    """
    if platform.system() == 'Windows':
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(folder), None, None, ctypes.pointer(free_bytes))
        return free_bytes.value  # / 1024 / 1024 // 1024
    else:
        st = os.statvfs(folder)
        return st.f_bavail * st.f_frsize  # / 1024 / 1024 // 1024