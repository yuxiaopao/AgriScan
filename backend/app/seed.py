from datetime import datetime, timedelta

from sqlalchemy import select

from .db import AppMeta, Detection, Plot, User
from .security import hash_password, verify_password


def initialize_data(db, settings):
    # The bootstrap administrator is explicitly managed by environment settings.
    # Preserve its identity when operators rotate credentials or rename the account.
    marker = db.get(AppMeta, "managed_admin_id")
    admin = db.get(User, marker.value) if marker else None
    configured = db.scalar(select(User).where(User.username == settings.admin_username))
    if configured and configured.role != "admin":
        raise RuntimeError("ADMIN_USERNAME 已被非管理员账号使用，请选择不同账号名。")
    if admin is None:
        admin = configured
        if admin is None:
            legacy_admins = db.scalars(select(User).where(User.role == "admin")).all()
            if len(legacy_admins) > 1:
                raise RuntimeError("存在多个未标记的管理员，请设置 ADMIN_USERNAME 为要管理的现有账号。")
            if legacy_admins:
                admin = legacy_admins[0]
    if admin is None:
        admin = User(
            username=settings.admin_username, password_hash=hash_password(settings.admin_password),
        )
        db.add(admin)
        db.flush()
    else:
        if configured and configured.id != admin.id:
            raise RuntimeError("ADMIN_USERNAME 与另一个已有账号冲突，请选择不同账号名。")
        admin.username = settings.admin_username
        if not verify_password(settings.admin_password, admin.password_hash):
            admin.password_hash = hash_password(settings.admin_password)
    db.merge(AppMeta(key="managed_admin_id", value=admin.id))
    if not settings.demo_mode:
        for other in db.scalars(select(User).where(User.id != admin.id)):
            if verify_password("admin12345", other.password_hash):
                raise RuntimeError("检测到其他仍使用演示密码的账号，请重置或移除该账号后启动生产环境。")
    if settings.demo_mode and not db.get(AppMeta, "demo_seed_v1"):
        plots = [
            Plot(id="plot-tomato", name="01 号番茄温室", crop="番茄", area=12.5, location="东区 · 智慧温室", manager="张明"),
            Plot(id="plot-rice", name="02 号水稻试验田", crop="水稻", area=36.0, location="南区 · 试验基地", manager="李华"),
            Plot(id="plot-corn", name="03 号玉米种植区", crop="玉米", area=28.0, location="西区 · 大田基地", manager="王芳"),
            Plot(id="plot-cucumber", name="04 号黄瓜大棚", crop="黄瓜", area=8.5, location="北区 · 连栋大棚", manager="张明"),
        ]
        db.add_all(plots)
        db.flush()
        # Explicit illustrative history, never returned as real model inference.
        demo_records = [
            ("番茄叶片 · 温室巡检", 0, "attention", "番茄早疫病", 0.967, 0),
            ("水稻长势 · 南区采样", 1, "healthy", "健康叶片", 0.989, 0),
            ("玉米叶片 · 田间巡查", 2, "healthy", "健康叶片", 0.982, 0),
            ("黄瓜叶片 · 北区采样", 3, "attention", "黄瓜霜霉病", 0.942, 1),
            ("番茄叶片 · 生长记录", 0, "healthy", "健康叶片", 0.993, 1),
            ("水稻叶片 · 定点巡检", 1, "healthy", "健康叶片", 0.981, 2),
            ("玉米叶片 · 生长记录", 2, "attention", "玉米叶斑病", 0.938, 2),
            ("番茄叶片 · 日常巡田", 0, "healthy", "健康叶片", 0.971, 3),
            ("黄瓜叶片 · 日常巡田", 3, "healthy", "健康叶片", 0.986, 3),
            ("水稻叶片 · 日常巡田", 1, "healthy", "健康叶片", 0.976, 4),
            ("玉米叶片 · 定点采样", 2, "healthy", "健康叶片", 0.985, 5),
            ("番茄叶片 · 温室采样", 0, "attention", "番茄早疫病", 0.951, 6),
        ]
        for index, (name, plot_index, status, result, confidence, days_ago) in enumerate(demo_records):
            plot = plots[plot_index]
            db.add(Detection(
                id=f"demo-{index + 1:03}", name=name, crop=plot.crop, plot_id=plot.id,
                status=status, result=result, confidence=confidence,
                created_at=datetime(2026, 10, 20, 3, 30) - timedelta(days=days_ago, minutes=index * 13),
                image_url=None, is_demo=True,
                note="演示样例，仅用于展示系统界面与工作流程；不是实际模型诊断。",
            ))
        db.add(AppMeta(key="demo_seed_v1", value="initialized"))
    db.commit()


KNOWLEDGE = [
    {
        "id": "tomato-early-blight", "title": "番茄早疫病：从叶片变化开始观察", "crop": "番茄",
        "category": "病害识别", "summary": "关注老叶上的同心轮纹病斑，及时记录田间湿度和病斑扩展情况。",
        "content": "番茄早疫病常从下部老叶开始出现褐色病斑，病斑可能形成同心轮纹。"
                   "巡检时拍摄叶片正反面、植株整体和相邻植株，并记录近期降雨、灌溉和通风情况。"
                   "改善通风，避免叶面长期湿润，清理病残体。相似症状也可能由其他因素造成，"
                   "应结合田间观察和专业植保人员的诊断确认；施药必须遵循当地登记标签。",
        "image": None,
        "sources": [{
            "title": "UMN Extension · Early blight",
            "url": "https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/early-blight-in-tomato-and-potato",
        }],
    },
    {
        "id": "rice-scouting", "title": "水稻巡田，把观察变成可追溯的记录", "crop": "水稻",
        "category": "田间管理", "summary": "固定采样路线，记录叶色、病斑分布与水肥条件，便于对比长势。",
        "content": "在田块不同位置选择代表性样点，保持相近的拍摄距离与光线条件。记录日期、"
                   "生育期、水层、叶色及异常植株的分布。对出现病斑的叶片同时拍摄近景与整株，"
                   "避免把虫害、机械损伤或营养问题误判为同一种病害。结合连续巡检记录咨询农技人员。",
        "image": None,
        "sources": [{
            "title": "IRRI · Rice Doctor",
            "url": "https://education.irri.org/wp-content/uploads/2022/10/RD-v2.pdf",
        }],
    },
    {
        "id": "corn-leaf", "title": "玉米叶斑观察与采样指南", "crop": "玉米",
        "category": "采样指南", "summary": "保留病斑边缘与叶脉细节，完整的图片信息有助于后续辅助识别。",
        "content": "采样时避开严重反光、模糊或被遮挡的叶片。拍摄一张完整叶片和一张病斑近景，"
                   "记录叶位及田间异常比例。不同病害和非生物胁迫都可能出现类似叶斑，"
                   "图片识别应作为辅助信息；重要管理决策需由植保人员结合现场确认。",
        "image": None,
        "sources": [{
            "title": "UMN Extension · Digital Crop Doc",
            "url": "https://extension.umn.edu/agriculture/crop-production/digital-crop-doc",
        }],
    },
    {
        "id": "cucumber-humidity", "title": "黄瓜棚室湿度与日常观察", "crop": "黄瓜",
        "category": "预防养护", "summary": "合理通风与水分管理，持续观察叶片正反面变化。",
        "content": "巡检时关注棚内通风、结露和叶面湿润持续时间，拍摄叶片正反面以保留完整信息。"
                   "棚室管理应结合当地气候、品种和生育期，避免单凭一张图片确定防治方案。"
                   "发现持续扩展的病斑时，应标记异常植株、单独记录，并请当地农技人员协助判断。",
        "image": None,
        "sources": [{
            "title": "UMN Extension · Downy mildew",
            "url": "https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/downy-mildew-of-cucurbits",
        }],
    },
]
