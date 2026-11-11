from desktop_ops import *
import sys

folder=Path('deliverables/project-demo/演示图片').resolve()
files=sorted(folder.glob(sys.argv[1]+'*'))
assert len(files)==1
focus()
click(int(sys.argv[2]),int(sys.argv[3]))
time.sleep(2.2)
assert win32gui.GetWindowText(win32gui.GetForegroundWindow()) in ('打开','Open')
hotkey(win32con.VK_MENU,ord('N'))
time.sleep(.7)
paste(str(files[0]))
time.sleep(.7)
hotkey(win32con.VK_RETURN)
time.sleep(1.5)
shot()
