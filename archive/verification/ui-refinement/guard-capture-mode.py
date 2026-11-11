from pathlib import Path
p=Path('E:/AgriScan/mobile/src/DetectPage.tsx');s=p.read_text(encoding='utf-8')
needle='    {!currentEnabled&&<div className="info-note" role="status">'
assert needle in s
s=s.replace(needle, '    {modeBlocked&&<p className="capture-message mode-change-note" role="status">{locked?\'当前观察尚未结束，请完成或停止当前操作后再切换方式。\':\'已保留当前观察，你可以重新选择需要的方式。\'}</p>}\n'+needle,1)
p.write_text(s,encoding='utf-8')
