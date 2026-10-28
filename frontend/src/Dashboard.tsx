import {Xiaohe} from './Xiaohe'
import {ArrowRight, ArrowUpRight, CircleAlert, Clock3, Download, Leaf, MapPin, Plus, ScanLine, ShieldCheck, Sprout} from 'lucide-react'
import {Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts'
import {CropIcon, DetectionTable, Empty} from './components'
import type {Dashboard as DashboardData, Detection, Page, Plot} from './types'

interface Props {
  data: DashboardData
  plots: Plot[]
  period: number
  setPeriod: (period: number) => void
  navigate: (page: Page) => void
  onSelect: (record: Detection) => void
  onExport: () => void
  onAttention: () => void
}

export default function Dashboard({data, plots, period, setPeriod, navigate, onSelect, onExport, onAttention}: Props) {
  const {stats} = data
  const completed = stats.healthy + stats.attention
  const healthRate = completed ? Math.round(stats.healthy / completed * 100) : 0
  const distributionTotal = data.distribution.reduce((sum, crop) => sum + crop.value, 0)
  const cards = [
    {title: '累计检测样本', number: stats.total, unit: '份', icon: ScanLine, tone: 'green', foot: '每一份样本，都让生长可见', detail: '所有样本'},
    {title: '健康作物样本', number: stats.healthy, unit: '份', icon: ShieldCheck, tone: 'sage', foot: `占已完成检测的 ${healthRate}%`, detail: '健康状态'},
    {title: '需要关注', number: stats.attention, unit: '份', icon: CircleAlert, tone: 'orange', foot: '及时查看异常，守护作物生长', detail: '查看记录'},
    {title: '待检测样本', number: stats.pending, unit: '份', icon: Clock3, tone: 'blue', foot: '接入模型后可继续处理', detail: '等待处理'},
  ]
  return <>

    <section className="welcome-banner">
      <div className="hero-grain"/>
      <div className="hero-copy"><span className="hero-label"><span/>让科技扎根田野</span><h2>用心观察，<br/>让每一片绿意安心生长。</h2><p>我是小禾，你的作物健康助手。<br className="mobile-break"/>一起发现田间的小变化，守护丰收的大期待。</p><button className="hero-button" onClick={() => navigate('detect')}>开始一次作物检测 <ArrowUpRight size={17}/></button></div>
      <div className="hero-art"><div className="hero-orbit orbit-one"/><div className="hero-orbit orbit-two"/><span className="floating-leaf leaf-one"><Leaf size={23}/></span><span className="floating-leaf leaf-two"><Sprout size={19}/></span><Xiaohe state="idle"/><span className="mascot-caption"><span className="tiny-spark">✦</span> 你好，我是小禾</span></div>
      <span className="hero-corner">GROW WITH CARE / AGRISCAN</span>
    </section>

    <div className="section-caption"><span><span className="live-dot"/>田间数据一览</span><span>全量记录统计 · 示例数据已标注</span></div>
    <section className="stats-grid" aria-label="样本统计">
      {cards.map(card => <div className={`stat-card ${card.tone}`} key={card.title}><div className="stat-top"><span>{card.title}</span><span className="stat-icon"><card.icon size={19}/></span></div><div className="stat-number">{card.number.toLocaleString()}<span>{card.unit}</span></div><div className="stat-bottom"><span>{card.foot}</span>{card.tone === 'orange' ? <button aria-label="查看需要关注的检测记录" onClick={onAttention}><ArrowUpRight size={16}/></button> : <span className="stat-decoration"/>}</div></div>)}
    </section>

    <div className="charts-grid">
      <section className="panel trend-panel"><div className="panel-header"><div><h2>检测趋势 <span className="muted-english">Detection trends</span></h2><p>持续关注作物健康变化</p></div><div className="segmented" aria-label="统计周期">{[7, 30].map(day => <button className={period === day ? 'selected' : ''} key={day} onClick={() => setPeriod(day)}>近 {day} 天</button>)}</div></div>
        <div className="chart-legend"><span><i className="legend-line green"/>检测样本</span><span><i className="legend-line lime"/>健康样本</span><span className="chart-unit">单位 / 份</span></div>
        <div className="trend-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.trend} margin={{top: 15, right: 10, bottom: 0, left: -26}}><defs><linearGradient id="totalGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4b916a" stopOpacity={.19}/><stop offset="100%" stopColor="#4b916a" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="4 5" vertical={false} stroke="#e9eee7"/><XAxis dataKey="label" tick={{fontSize: 11, fill: '#98a294'}} tickLine={false} axisLine={false} tickMargin={12} minTickGap={20}/><YAxis allowDecimals={false} tick={{fontSize: 11, fill: '#98a294'}} tickLine={false} axisLine={false}/><Tooltip contentStyle={{borderRadius: 10, border: '1px solid #e3e9df', fontSize: 12}}/><Area type="monotone" name="检测样本" dataKey="total" stroke="#3a7c54" strokeWidth={2.5} fill="url(#totalGradient)" activeDot={{r: 5, strokeWidth: 3, stroke: '#fff'}}/><Area type="monotone" name="健康样本" dataKey="healthy" stroke="#bdcf8a" strokeWidth={2} strokeDasharray="5 4" fill="none"/></AreaChart></ResponsiveContainer></div>
      </section>
      <section className="panel distribution-panel"><div className="panel-header"><div><h2>作物分布 <span className="muted-english">Crop overview</span></h2><p>每一种作物，都值得被关注</p></div><Sprout size={20} className="muted-icon"/></div>
        {distributionTotal ? <><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data.distribution} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={62} outerRadius={82} paddingAngle={4} cornerRadius={4} stroke="none">{data.distribution.map((entry, index) => <Cell key={entry.name} fill={['#327554', '#8eb793', '#b7cc94', '#e8cc85', '#dbe7d2'][index % 5]}/>)}</Pie><Tooltip contentStyle={{borderRadius: 10, fontSize: 12}}/></PieChart></ResponsiveContainer><div className="donut-center"><span>已管理作物</span><strong>{data.distribution.length}<small>种</small></strong></div></div><div className="crop-legend">{data.distribution.map((crop, index) => <div key={crop.name}><span><i style={{background: ['#327554', '#8eb793', '#b7cc94', '#e8cc85', '#dbe7d2'][index % 5]}}/>{crop.name}</span><b>{Math.round(crop.value / distributionTotal * 100)}<small>%</small></b></div>)}</div></> : <Empty title="还没有作物数据" description="上传样本后，这里将展示作物分布。"/>}
      </section>
    </div>

    <div className="bottom-grid">
      <section className="panel recent-panel"><div className="panel-header"><div><h2>最近检测 <span className="count-pill">{Math.min(4, data.recent.length)}</span></h2><p>田间每一刻，记录都在这里</p></div><button className="text-button" onClick={() => navigate('records')}>全部记录 <ArrowRight size={15}/></button></div>{data.recent.length ? <DetectionTable records={data.recent.slice(0, 4)} onSelect={onSelect}/> : <Empty title="第一份检测，从这里开始" description="添加一张作物图片，建立你的田间健康档案。"/>}<div className="table-footer"><span><ShieldCheck size={13}/>检测记录已持久化保存</span><button onClick={onExport}><Download size={13}/>导出记录</button></div></section>
      <section className="panel plots-overview"><div className="panel-header"><div><h2>我的地块</h2><p>脚下的土地，心中的牵挂</p></div><button className="icon-button subtle" aria-label="查看所有地块" onClick={() => navigate('plots')}><ArrowUpRight size={18}/></button></div><div className="mini-plots">{plots.slice(0, 3).map(plot => <button key={plot.id} onClick={() => navigate('plots')}><CropIcon crop={plot.crop} size={37}/><div><strong>{plot.name}</strong><span>{plot.crop} · {plot.area} 亩</span></div><span className="plot-tag"><MapPin size={11}/>在管</span></button>)}</div><button className="add-plot-link" onClick={() => navigate('plots')}><Plus size={14}/>管理我的地块</button></section>
    </div>
  </>
}
