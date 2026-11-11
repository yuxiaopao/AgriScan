from desktop_ops import *
import sys

focus();click(1820,920);hotkey(win32con.VK_CONTROL,win32con.VK_END);time.sleep(1.4)
click(1100,1080);hotkey(win32con.VK_CONTROL,ord('A'));paste('课程项目演示：'+sys.argv[1]+'叶片样本')
click(2362,1260)
time.sleep(5)
shot()
