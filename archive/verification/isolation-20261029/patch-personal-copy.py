from pathlib import Path

changes={
'frontend/src/App.tsx':[("canManage={user?.role === 'admin'}",'canManage={Boolean(user)}'),('数据已保存至工作空间','数据已保存至我的账户')],
'frontend/src/Dashboard.tsx':[('全量记录统计 · 示例数据已标注','仅统计我的记录 · 示例数据已标注'),('田间数据一览','我的田间数据'),("detail: '所有样本'","detail: '我的样本'")],
'frontend/src/Pages.tsx':[('管理中的地块','我的地块'),('地块档案由管理员维护，你可以查看地块和关联检测样本。','登录后可以创建和维护自己的地块。'),('普通成员 · 浏览共享数据与上传样本','普通成员 · 管理我的地块与检测记录'),('管理员 · 管理样本、地块与模型','管理员 · 此处仅管理我的地块与样本')],
'mobile/src/WorkspacePages.tsx':[('工作空间共享记录，让每一次观察有迹可循。','只展示当前账户的检测记录，让每一次观察有迹可循。'),('查看共享地块，在检测时关联采样位置。','查看我自己的地块，在检测时关联采样位置。'),('共享观察记录','我的观察记录'),('管理中的地块','我的地块'),('业务数据属于共享工作空间，小禾对话仅当前账户可读取。','检测记录、地块与小禾对话按账户隔离；管理人员通过独立管理端维护。'),('调整关键词，或联系管理员完善地块资料。','调整关键词，或在网页版创建和维护自己的地块。')]
}
for name,replacements in changes.items():
    path=Path(name);source=path.read_text(encoding='utf-8')
    for old,new in replacements:
        if old not in source and new not in source:
            print('Preserved concurrently changed copy in '+name)
            continue
        source=source.replace(old,new)
    path.write_text(source,encoding='utf-8')
    print('Updated '+name)
