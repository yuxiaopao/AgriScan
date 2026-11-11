import argparse
import ctypes
import json
import time
from pathlib import Path

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import win32api
import win32clipboard
import win32con
import win32gui
from PIL import ImageGrab

ROOT = Path(__file__).parent

def chrome_window():
    found = []
    def collect(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).endswith(' - Google Chrome'):
            found.append(h)
    win32gui.EnumWindows(collect, None)
    if len(found) != 1:
        raise RuntimeError(f'Expected one visible Chrome window, found {len(found)}')
    return found[0]

def key(code, up=False):
    win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP if up else 0, 0)

def hotkey(*codes):
    for code in codes: key(code)
    time.sleep(.08)
    for code in reversed(codes): key(code, True)
    time.sleep(.3)

def paste(text):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    hotkey(win32con.VK_CONTROL, ord('V'))

def click(x,y):
    win32api.SetCursorPos((x,y));time.sleep(.12)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
    time.sleep(.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0)

def focus():
    h=chrome_window()
    hotkey(win32con.VK_MENU)
    win32gui.ShowWindow(h,win32con.SW_MAXIMIZE)
    win32gui.SetForegroundWindow(h)
    time.sleep(.6)
    return h

def shot(name='current.png'):
    p=ROOT/name
    im=ImageGrab.grab();im.save(p)
    im.resize((1280,800)).save(ROOT/'preview.png')
    print(json.dumps({'screenshot':str(p),'size':im.size,'foreground':win32gui.GetWindowText(win32gui.GetForegroundWindow()),'chrome_hwnd':chrome_window()},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action');parser.add_argument('values',nargs='*');a=parser.parse_args()
    if a.action not in ('shot','focus'):
        fg=win32gui.GetForegroundWindow()
        if fg!=chrome_window() and win32gui.GetWindowText(fg) not in ('打开','Open'):
            focus()
    if a.action=='focus': focus()
    elif a.action=='click': click(*map(int,a.values[:2]))
    elif a.action=='paste': paste(a.values[0])
    elif a.action=='key': hotkey(*[int(v,0) for v in a.values])
    elif a.action=='scroll': win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL,0,0,int(a.values[0]),0)
    elif a.action=='navigate':
        focus();hotkey(win32con.VK_CONTROL,ord('L'));paste(a.values[0]);hotkey(win32con.VK_RETURN);time.sleep(2.5)
    elif a.action!='shot': raise ValueError(a.action)
    time.sleep(.4)
    shot()
