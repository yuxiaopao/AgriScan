from pathlib import Path

p=Path('frontend/src/Access.tsx');s=p.read_text(encoding='utf-8')
s=s.replace('ArrowRight, Leaf, ScanLine', 'ArrowRight, Eye, EyeOff, Leaf, ScanLine')
s=s.replace('  const [busy, setBusy] = useState(false)', '  const [busy, setBusy] = useState(false)\n  const [showPassword, setShowPassword] = useState(false)')
s=s.replace("setMessage('注册成功！现在可以前往登录。')", "setMessage('账户已创建，现在可以前往登录。')")
s=s.replace('<label>密码<input name="password" required type="password"', '<label>密码<div className="password-field"><input name="password" required type={showPassword ? \'text\' : \'password\'}')
s=s.replace("placeholder={register?'至少 10 位字符':'请输入密码'}/></label>", "placeholder={register?'至少 10 位字符':'请输入密码'}/><button type=\"button\" className=\"icon-button password-toggle\" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>")
p.write_text(s,encoding='utf-8')

p=Path('frontend/src/App.tsx');s=p.read_text(encoding='utf-8')
s=s.replace('  const accountArea = useRef<HTMLDivElement>(null)', '  const sidebarRef = useRef<HTMLElement>(null)\n  const menuButton = useRef<HTMLButtonElement>(null)\n  const accountArea = useRef<HTMLDivElement>(null)')
s=s.replace('  useEffect(() => {\n    if (!accountOpen) return', '''  useEffect(() => {
    if (!menu) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebarRef.current?.querySelector<HTMLElement>('a[aria-current="page"], a')?.focus()
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const items = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') || [])
      if (event.shiftKey && document.activeElement === items[0]) {event.preventDefault(); items[items.length - 1]?.focus()}
      if (!event.shiftKey && document.activeElement === items[items.length - 1]) {event.preventDefault(); items[0]?.focus()}
    }
    document.addEventListener('keydown', trap)
    return () => {document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', trap); menuButton.current?.focus()}
  }, [menu])
  useEffect(() => {
    if (!accountOpen) return''',1)
s=s.replace('<aside className={`sidebar ${menu ? \'open\' : \'\'}`}>', '<aside ref={sidebarRef} id="workspace-navigation" className={`sidebar ${menu ? \'open\' : \'\'}`}>')
s=s.replace('<div className="main-shell"><header', '<div className="main-shell" inert={menu || undefined}><header')
s=s.replace('<button className="icon-button mobile-menu" onClick={() => setMenu(true)} aria-label="打开导航">', '<button ref={menuButton} className="icon-button mobile-menu" onClick={() => setMenu(true)} aria-label="打开导航" aria-expanded={menu} aria-controls="workspace-navigation">')
s=s.replace('{loading ? <Loading/> : data ? <MotionSurface key={page} page={page}>', '''{loading ? <Loading/> : data ? <MotionSurface key={page} page={page}>
        {page === 'dashboard' ? <h1 className="sr-only">总览工作台</h1> : <div className="page-intro"><div><span className="eyebrow">禾观 · 田间工作空间</span><h1>{currentPageName}</h1><p>{({detect:'从一张清晰的照片开始，记录作物的真实变化。', records:'筛选、对照与导出，让每一次观察都有迹可循。', plots:'把照片与土地连接起来，持续关注每一块地。', knowledge:'观察之外，多了解一点作物与养护。', models:'查看识别能力、覆盖范围和服务运行状态。', settings:'调整工作空间，让记录更合你的习惯。'} as Record<string,string>)[page]}</p></div></div>}''')
p.write_text(s,encoding='utf-8')
