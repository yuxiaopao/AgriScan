from pathlib import Path

p=Path('frontend/src/Pages.tsx');s=p.read_text(encoding='utf-8')
old='</section>{children}<div className="model-grid">'
assert s.count(old)==1
s=s.replace(old,'</section>{children}<RunningModels model={model}/><div className="model-grid">',1)
s=s.replace('<Layers3 size={17}/>活动模型','<Layers3 size={17}/>主要识别模型').replace('<Settings2 size={17}/>模型适配器','<Settings2 size={17}/>主模型适配器')
p.write_text(s,encoding='utf-8')
p=Path('admin/src/Admin.tsx');s=p.read_text(encoding='utf-8');start=s.index('function ModelsAdmin(');end=s.index('\nfunction AuditTable(',start)
s=s[:start]+'''function ModelsAdmin({revision,changed}:CommonProps){
  const state=useLoad<ModelInfo>('/models',revision)
  return <>
    {state.error&&<ErrorBox text={state.error} retry={state.reload}/>}
    <Panel><div className="adm-panel-heading"><div><h2>当前运行模型</h2><p>目标检测与分类复核分别显示实际加载状态</p></div><FlaskConical size={20}/></div>
      {state.loading?<Busy/>:state.data?.active?<div className="adm-running-models"><RunningModels model={state.data}/></div>:!state.error&&<EmptyState title="尚未启用识别模型" detail="已上传权重需要验证并完成推理适配后才能启用。"/>}
    </Panel>
    <WeightManager onChange={changed} canManage/>
    <div className="adm-info"><ShieldCheck size={17}/><span>上传登记列表与实际运行模型分别维护。登记为空不表示推理模型未加载；上传不会自动切换模型。历史检测保留当次两模型快照。</span></div>
  </>
}
''' + s[end:];p.write_text(s,encoding='utf-8')
p=Path('frontend/src/Integrations.tsx');s=p.read_text(encoding='utf-8')
s=s.replace('我的训练权重','上传权重登记').replace('还没有训练权重','暂无额外上传登记')
p.write_text(s,encoding='utf-8')
print('Model pages now show active components independently of the upload registry.')
