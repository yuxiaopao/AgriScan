from pathlib import Path
p=Path('E:/AgriScan/mobile/src/WorkspacePages.tsx')
s=p.read_text(encoding='utf-8')
s=s.replace("data.model?'当前为样本采集模式':'服务状态待确认'", "data.model?(config.features.image_detection?'当前为样本采集模式':'图片采集暂时暂停'):'服务状态待确认'")
s=s.replace("ready?'种作物可识别':'种作物可采集'", "ready?'种作物可识别':config.features.image_detection?'种作物可采集':'种作物已配置'")
s=s.replace('当前可保存照片和采样备注；模型启用前，不会生成病害判断。', "{config.features.image_detection?'当前可保存照片和采样备注；模型启用前，不会生成病害判断。':'图片采集暂时暂停，仍可回看已经保存的观察记录。'}")
s=s.replace("{cropCount}</strong>{ready?'可识别作物':'可采集作物'}", "{data.model?cropCount:'—'}</strong>{ready?'可识别作物':data.model?(config.features.image_detection?'可采集作物':'已配置作物'):'状态待确认'}")
p.write_text(s,encoding='utf-8')
