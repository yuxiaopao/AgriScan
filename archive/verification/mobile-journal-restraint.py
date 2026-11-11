from pathlib import Path
p=Path('E:/AgriScan/mobile/src/WorkspacePages.tsx')
s=p.read_text(encoding='utf-8')
s=s.replace('<span className="journal-page-label">每一次观察，都有迹可循</span>', '')
s=s.replace('<span className="journal-page-label">把观察与土地连起来</span>', '')
s=s.replace('<div className="journal-secondary-modes" aria-label=', '<div className="journal-secondary-modes" role="group" aria-label=')
p.write_text(s,encoding='utf-8')
