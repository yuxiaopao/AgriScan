from desktop_ops import *
import re

text=Path('.runtime/server-admin-access.txt').read_text(encoding='utf-8-sig')
values={m.group(1).lower():m.group(2).strip() for m in re.finditer(r'^(Username|Password)\s*[:=]\s*(.+)$',text,re.M)}
assert 'username' in values and 'password' in values
focus()
assert '登录' in win32gui.GetWindowText(win32gui.GetForegroundWindow())
click(1630,822);paste(values['username'])
click(1630,952);paste(values['password'])
click(1670,1040)
win32clipboard.OpenClipboard()
try:win32clipboard.EmptyClipboard()
finally:win32clipboard.CloseClipboard()
time.sleep(6)
shot()
