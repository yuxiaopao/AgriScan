import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import sharp from 'sharp';
const ROOT='E:/AgriScan';
const BUILD=path.join(ROOT,'.runtime/defense-ppt-build');
const OUT=path.join(ROOT,'deliverables/defense');
const SKILL='C:/Users/18984/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22136/skills/presentations';
const PY='C:/Users/18984/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const {applyPresentationChartFont,finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const FONT='Microsoft YaHei';
const C={paper:'#F7F7EF',white:'#FFFFFF',ink:'#193D30',green:'#2D704D',mint:'#BDE6B5',sage:'#91B77B',muted:'#697D6F',line:'#D9E1D4',dark:'#113B2D',dark2:'#24513C',gold:'#C4A66C',light:'#E9EFE2',soft:'#F1F4EA'};
const p=Presentation.create({slideSize:{width:1280,height:720}});
let notes=[];try{notes=JSON.parse(await fs.readFile(path.join(BUILD,'notes.json'),'utf8'));}catch{}
const allTexts=[];
function rect(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
function text(s,x,y,w,h,value,size=26,color=C.ink,bold=false,align='left',name=''){
 const q=s.shapes.add({geometry:'textbox',name:name||`text-${allTexts.length}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 q.text=value;q.text.style={fontSize:size,typeface:FONT,color,bold,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};
 allTexts.push({slide:p.slides.items.length,text:value});return q;
}
function rule(s,x,y,w,color=C.line){rect(s,x,y,w,1.2,color);}
async function img(s,name,x,y,w,h,fit='contain'){
 const file=path.join(BUILD,'assets',name+'.png');
 return s.images.add({blob:new Uint8Array(await fs.readFile(file)),contentType:'image/png',position:{left:x,top:y,width:w,height:h},fit,alt:name});
}
function slide(title,section,dark=false){
 const s=p.slides.add();s.background.fill=dark?C.dark:C.paper;
 const num=p.slides.items.length;
 text(s,64,34,1040,26,section,16,dark?C.mint:C.muted,false);
 text(s,64,82,1150,72,title,43,dark?C.white:C.ink,true,'left','slide-title');
 rule(s,64,663,1152,dark?C.dark2:C.line);
 text(s,64,679,700,22,'禾观 AgriScan  /  课程项目答辩',14,dark?C.mint:C.muted);
 text(s,1148,677,68,26,String(num).padStart(2,'0'),17,dark?C.mint:C.muted,false,'right');
 const n=notes.find(x=>x.slide===num);
 if(n)s.speakerNotes.text=n.notes+'\n\n资料依据：\n'+n.sources.join('\n');
 return s;
}
function table(s,x,y,w,h,values,widths,font=23){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
 t.styleOptions={headerRow:true,bandedRows:false};t.borders.assign({fill:C.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.green:(r%2?C.white:C.soft);
  cell.text.style={fontSize:font,typeface:FONT,color:r===0?C.white:C.ink,bold:r===0,verticalAlignment:'middle',wrap:'square',insets:12};
 }
 t.rows[0].height=58;
 return t;
}
function item(s,num,title,body,x,y,w=330,dark=false){
 text(s,x,y,w,49,num,39,dark?C.mint:C.sage,true);
 text(s,x,y+62,w,40,title,29,dark?C.white:C.ink,true);
 text(s,x,y+118,w,145,body,25,dark?C.mint:C.muted);
}
function lineItem(s,index,title,body,y,dark=false){
 const ink=dark?C.white:C.ink, muted=dark?C.mint:C.muted;
 text(s,64,y,64,45,index,31,dark?C.sage:C.green,true);
 text(s,150,y,300,44,title,29,ink,true);
 text(s,485,y,710,86,body,25,muted);
 rule(s,150,y+106,1044,dark?C.dark2:C.line);
}

// 01 cover
{
 const s=p.slides.add();s.background.fill=C.dark;
 text(s,68,49,650,35,'农业智能检测平台  /  课程答辩',20,C.mint);
 text(s,64,167,660,111,'禾观 AgriScan',68,C.white,true);
 text(s,68,299,630,105,'基于深度学习的\n作物叶片健康观察系统',37,C.white);
 text(s,68,459,590,68,'让每次识别都有依据\n让每次观察都留下记录',25,C.mint);
 rule(s,68,575,590,C.dark2);
 text(s,68,596,650,60,'［学校 / 课程名称］\n四人项目组    ［指导教师］',19,C.mint);
 await img(s,'mascot',755,83,450,560);
 const n=notes.find(x=>x.slide===1);if(n)s.speakerNotes.text=n.notes+'\n资料依据：'+n.sources.join('\n');
}
// 02 agenda
{
 const s=slide('答辩内容','汇报导览');
 const sections=[['01','项目介绍','背景、意义与数据集'],['02','团队介绍','四人职责与协作方式'],['03','实现过程','技术路线与关键问题'],['04','项目结果','实验指标与系统演示'],['05','课程收获','技术能力与工程意识'],['06','创新与改进','已实现特色与后续计划']];
 sections.forEach(([n,t,b],i)=>{const x=64+(i%3)*400,y=195+Math.floor(i/3)*225;text(s,x,y,60,46,n,34,C.sage,true);text(s,x+80,y+2,290,45,t,30,C.ink,true);text(s,x+80,y+66,300,70,b,23,C.muted);rule(s,x,y+165,350);});
}
// 03 background
{
 const s=slide('作物健康观察中的实际问题','01  项目介绍');
 item(s,'01','症状相似，判断有门槛','病害与健康状态依赖经验，\n单张照片容易产生误判。',64,202,343);
 item(s,'02','结果分散，复查难追溯','照片、地块与检测结论缺少\n统一记录，后续观察难比较。',463,202,343);
 item(s,'03','识别之后，还需要解释','用户需要知道观察重点、\n复拍方式和下一步处理建议。',862,202,343);
 rule(s,64,536,1152);text(s,64,564,1140,58,'项目目标：提供易使用、可追溯的作物健康观察工具',31,C.green,true);
}
// 04 positioning
{
 const s=slide('禾观的定位与应用意义','01  项目介绍');
 text(s,64,190,650,112,'叶片识别与观察记录\n在同一个工作空间完成',39,C.ink,true);
 text(s,64,332,650,134,'面向课程实验与农场观察场景，\n将识别结果、地块档案和小禾解读\n组织成可复查的观察记录。',27,C.muted);
 text(s,64,514,615,94,'使用价值\n降低操作门槛，为复检保留依据',27,C.green,true);
 await img(s,'think',830,164,320,367);
 text(s,805,554,365,61,'定位为辅助观察\n处理建议仍需结合现场确认',21,C.muted,false,'center');
}
// 05 dataset
{
 const s=slide('PlantVillage 叶片图像数据集','01  项目介绍');
 [['54,305','图像总数'],['14','作物种类'],['38','健康与病害类别']].forEach(([n,l],i)=>{let x=64+i*400;text(s,x,180,350,80,n,60,C.green,true);text(s,x,270,350,42,l,24,C.muted);});
 for(let i=0;i<4;i++){await img(s,'leaf'+i,64+i*290,343,250,220);}
 ['苹果黑星病','苹果健康','玉米普通锈病','番茄早疫病'].forEach((v,i)=>text(s,64+i*290,578,250,40,v,23,C.ink,false,'center'));
}
// 06 split
{
 const s=slide('数据划分与防泄漏处理','01  项目介绍');
 const chart=s.charts.add('bar',{position:{left:54,top:190,width:680,height:355},categories:['独立测试集','验证集','训练集'],series:[{name:'图像数',values:[10999,5485,37821],fill:C.green}],barOptions:{direction:'bar',gapWidth:90},hasLegend:false,chartFill:C.paper,plotAreaFill:C.paper,xAxis:{visible:true,textStyle:{fontSize:22,fill:C.ink},line:{fill:'none',width:0}},yAxis:{textStyle:{fontSize:17,fill:C.muted},line:{fill:'none',width:0},majorGridlines:null},dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'#,##0',textStyle:{fontSize:22,fill:C.green,bold:true}}});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,800,197,400,45,'按叶片分组，再核验哈希',28,C.ink,true);
 text(s,800,273,400,124,'同一叶片与重复文件\n不跨训练、验证和测试集合。\n290 张图像调整至测试集。',25,C.muted);
 text(s,800,440,380,82,'跨集合叶片重叠  0\nSHA256 重叠  0',27,C.green,true);
 text(s,64,594,1110,40,'验证集选择最佳模型，独立测试集只用于最终报告',27,C.ink,true);
}
// 07 team
{
 const s=slide('四人团队分工','02  团队介绍');
 table(s,64,185,1152,374,[['成员','主要职责','负责模块','交付成果'],['成员 A\n［姓名］','项目统筹与后端','FastAPI、数据模型\n认证与系统集成','API、数据库\n接口联调'],['成员 B\n［姓名］','数据与模型','数据处理、模型训练\n评估与 ONNX 导出','数据报告、模型\n实验指标'],['成员 C\n［姓名］','桌面前端与 IP','React 工作台\n小禾视觉与交互','桌面页面\nIP 主题素材'],['成员 D\n［姓名］','移动端与测试发布','Android APP\n回归测试与部署','测试 APK\n验收报告与演示']], [142,255,385,370],22);
 text(s,64,593,1152,42,'协作方式：接口约定、模块联调、交叉验收、共同答辩',26,C.green,true);
 text(s,64,637,1150,20,'建议分工方案，可按实际贡献调整成员姓名与职责。',15,C.muted);
}
// 08 process
{
 const s=slide('项目开发过程','03  实现过程');
 const parts=[['1','需求与原型','明确叶片观察场景\n确定工作台与小禾形象'],['2','数据与实验','整理 PlantVillage\n训练与评估分类模型'],['3','服务与界面','接入真实推理 API\n打通保存与查询流程'],['4','集成与完善','接入检测模型与 APP\n修复异常并交叉验收']];
 parts.forEach(([n,t,b],i)=>{const x=64+i*296;text(s,x,210,250,78,n,60,C.sage,true);rule(s,x,309,250);text(s,x,341,260,46,t,29,C.ink,true);text(s,x,416,265,138,b,24,C.muted);});
 text(s,64,588,1140,38,'每个阶段保留可运行产物，并用真实接口验证下一步',27,C.green,true);
}
// 09 architecture
{
 const s=slide('系统架构与模块职责','03  实现过程');
 table(s,64,182,1152,398,[['层级','技术与模块','职责'],['应用入口','桌面 React  /  Android Capacitor\n独立管理控制台','桌面操作、手机采集\n管理与配置'],['业务服务','FastAPI 共享 API','鉴权、检测流程\n记录、地块与对话'],['智能能力','ONNX Runtime  /  小禾图片解读','执行真实模型推理\n外部服务补充照片解读'],['数据存储','MySQL  /  Redis','保存业务与私人对话\n看板短期缓存']], [155,532,465],24);
 text(s,64,602,1135,37,'模型识别与 AI 解读分别保存，解读失败时保留原检测结果',26,C.green,true);
}
// 10 training
{
 const s=slide('分类模型的训练与选择','03  实现过程');
 const csv=(await fs.readFile(path.join(ROOT,'runs/classify/plantvillage-yolo26m/results.csv'),'utf8')).trim().split(/\r?\n/).slice(1).map(x=>x.split(',').map(Number));
 const chart=s.charts.add('scatter',{position:{left:54,top:208,width:740,height:350},series:[{name:'验证集 Top-1',xValues:csv.map(x=>x[0]),values:csv.map(x=>x[3]),line:{fill:C.green,width:3},marker:{symbol:'none'}}],hasLegend:false,scatterOptions:{style:'line'},chartFill:C.paper,plotAreaFill:C.paper,xAxis:{min:0,max:40,majorUnit:5,numberFormatCode:'0',textStyle:{fontSize:18,fill:C.muted},line:{fill:C.line,width:1},title:{text:'训练轮数',textStyle:{fontSize:19,fill:C.muted}}},yAxis:{min:0.8,max:1,majorUnit:0.05,numberFormatCode:'0%',textStyle:{fontSize:19,fill:C.muted},majorGridlines:{fill:C.line,width:1}}});
 applyPresentationChartFont(chart,{fontFamily:FONT});
 text(s,850,188,350,86,'YOLO26m 骨干\n迁移至 38 类分类头',28,C.ink,true);
 text(s,850,319,350,184,'224 × 224 输入\nAdamW，batch 32\nAMP 混合精度\n40 轮完整训练',25,C.muted);
 text(s,850,548,350,69,'第 37 轮达到\n最高验证 Top-1',25,C.green,true);
}
// 11 detect
{
 const s=slide('目标检测模型的接入','03  实现过程');
 text(s,64,187,760,87,'用户提供的 YOLO26m Detect 权重\n转换为 FP32 ONNX 推理模型',32,C.ink,true);
 table(s,64,310,1152,233,[['技术环节','实现方式'],['输入与预处理','640 × 640，letterbox 等比例缩放与填充'],['输出与展示','真实目标框、目标置信度与类别，不归一化为分类概率'],['发布与核验','模型清单 + SHA256；五张样例核验数值与原图框坐标']], [240,912],24);
 text(s,64,581,1145,54,'当前目标检测模型尚无独立检测集 mAP，分类成绩单独报告',25,C.green,true);
}
// 12 problems
{
 const s=slide('关键问题与解决方法','03  实现过程');
 lineItem(s,'01','旧权重导出异常','恢复正确的 end2end 分支，在模型融合前修复兼容问题，核对 PyTorch 与 ONNX 输出。',188);
 lineItem(s,'02','框位置与原图不一致','统一 letterbox 预处理与逆变换，按保存原图坐标展示目标框。',334);
 lineItem(s,'03','检测结果与地块冲突','核对全部目标的作物类型，拒绝混样关联并回滚整次修改，补充回归测试。',480);
}
// 13 mascot design
{
 const s=slide('小禾 IP 与交互设计','03  实现过程');
 await img(s,'mascot',65,168,290,380);
 text(s,405,183,782,58,'农业机器人形象贯穿整套交互',35,C.ink,true);
 text(s,405,265,784,88,'森林绿与象牙白构成主色，叶芽与放大镜\n对应“生长”和“观察”的产品含义。',25,C.muted);
 for(const [i,n] of ['apple','corn','tomato','grape','potato'].entries())await img(s,n,398+i*160,369,136,164);
 text(s,405,557,790,80,'17 套作物主题与对应角色素材\n模型覆盖 14 种作物，水稻、小麦、黄瓜仅作主题',23,C.green,true);
}
// 14 results
{
 const s=slide('独立测试集分类结果','04  项目结果',true);
 text(s,64,177,600,123,'99.67%',94,C.white,true);
 text(s,68,311,600,48,'Top-1 准确率',30,C.mint);
 text(s,713,177,498,123,'99.56%',83,C.mint,true);
 text(s,718,311,478,48,'宏平均 F1',30,C.mint);
 rule(s,64,402,1152,C.dark2);
 text(s,64,437,690,100,'10,999 张封存测试图像\n36 张分类错误',30,C.white,true);
 text(s,820,433,385,139,'薄弱类别：玉米灰斑病\nF1 94.98%\n需要进一步分析混淆样本',25,C.mint);
 text(s,64,584,1152,48,'以上为 PlantVillage 单叶分类实验，田间泛化仍需独立验证',25,C.mint);
}
// 15 actual detection
{
 const s=slide('真实模型识别与结果保存','04  项目结果');
 await img(s,'detect-result',64,179,835,444);
 text(s,950,196,265,75,'苹果黑星病',31,C.ink,true);
 text(s,950,292,260,95,'84.60%\n该目标置信度',31,C.green,true);
 text(s,950,435,270,150,'原图与真实框并排展示\n检测结论保存到记录\n小禾可继续解读照片',24,C.muted);
 text(s,64,633,1130,22,'实际界面截取。单张样例展示系统流程，不作为模型整体精度。',16,C.muted);
}
// 16 clients
{
 const s=slide('桌面与移动端成果','04  项目结果');
 await img(s,'desktop',64,185,768,383,'cover');
 text(s,64,587,760,43,'桌面工作台：总览、检测、记录与地块',25,C.ink,true);
 await img(s,'mobile-home',906,176,208,450);
 text(s,869,632,330,25,'独立 Android 测试 APK',19,C.green,true,'center');
}
// 17 management
{
 const s=slide('管理控制台与数据闭环','04  项目结果');
 await img(s,'admin',64,188,770,434);
 text(s,890,196,320,42,'独立管理员入口',29,C.ink,true);
 text(s,890,280,320,133,'用户与权限管理\n地块、检测与知识维护\n模型登记与服务配置',24,C.muted);
 text(s,890,453,320,130,'记录保留图片、候选\n目标框与模型快照\n支持筛选和 CSV 导出',24,C.green,true);
 text(s,64,632,1110,22,'界面中的记录数量为示例工作空间状态，不代表实际用户规模。',16,C.muted);
}
// 18 validation
{
 const s=slide('系统验证与能力边界','04  项目结果');
 text(s,64,185,670,120,'192',88,C.green,true);
 text(s,68,313,675,51,'项后端自动化回归通过',31,C.ink,true);
 text(s,68,386,650,83,'另 1 项因 Windows 符号链接权限跳过\n记录日期：2026 年 10 月 28 日',23,C.muted);
 text(s,790,187,420,49,'已核验',29,C.ink,true);
 text(s,790,251,420,110,'真实推理与结果持久化\n接口鉴权与异常输入\nMySQL、Redis 与服务健康',24,C.muted);
 rule(s,790,391,420);
 text(s,790,420,420,48,'仍需验证',29,C.ink,true);
 text(s,790,484,420,124,'独立检测集 mAP 与田间泛化\nAndroid 真机相机与权限\n高并发与长期运行稳定性',24,C.muted);
 text(s,64,585,675,46,'目标框当前不提供病斑精确面积',26,C.green,true);
}
// 19 learning
{
 const s=slide('课程收获','05  课程收获');
 const rows=[['数据与实验','理解数据泄漏、验证集选模与独立测试的区别。'],['模型与部署','掌握训练、导出、预处理一致性和真实接口接入。'],['系统与协作','完成前后端、移动端与数据库的跨模块联调。'],['质量与表达','用回归测试复现问题，按证据说明结果与能力边界。']];
 rows.forEach(([t,b],i)=>{const y=192+i*111;text(s,64,y,310,42,t,30,C.green,true);text(s,410,y,792,75,b,25,C.ink);if(i<3)rule(s,64,y+84,1152);});
}
// 20 innovation
{
 const s=slide('项目创新与特色','06  创新与改进',true);
 item(s,'01','IP 驱动的状态反馈','小禾形象与作物主题结合，\n用角色状态表达观察、思考\n与结果反馈。',64,203,335,true);
 item(s,'02','识别与解释相互衔接','真实模型输出保留原始结果，\n小禾基于照片补充解读，\n并提供复拍与复检建议。',464,203,335,true);
 item(s,'03','结果可追溯','保留目标框与模型快照\n支持跨端查看与数据导出\n便于复核与问题追溯',864,203,335,true);
 text(s,64,581,1140,50,'创新主要体现于产品交互与工程整合，算法采用现有模型体系',24,C.mint);
}
// 21 future
{
 const s=slide('后续改进路线','06  创新与改进');
 const data=[['优先 1','数据与可信评估','采集真实田间图像\n建立独立检测集与 mAP\n分析误判和未知类别'],['优先 2','农技知识与复查','引入带来源的知识检索\n建立同株 / 同叶复拍记录\n评估分割与严重度量化'],['优先 3','实用性与性能','完成 Android 真机验收\n探索弱网与端侧轻量化\n完善并发、备份和监控']];
 data.forEach(([n,t,b],i)=>{const x=64+i*400;text(s,x,201,350,42,n,24,C.muted);rule(s,x,265,350);text(s,x,299,350,48,t,30,C.ink,true);text(s,x,389,350,174,b,25,C.muted);});
 text(s,64,603,1152,32,'本页为后续计划，按“先验证，再扩展”的顺序推进',23,C.green,true);
}
// 22 thanks
{
 const s=p.slides.add();s.background.fill=C.dark;
 text(s,68,62,720,35,'禾观 AgriScan  /  农业智能检测平台',21,C.mint);
 text(s,64,219,780,104,'感谢聆听',68,C.white,true);
 text(s,68,353,700,80,'恳请各位老师批评指正',33,C.mint);
 text(s,68,526,675,65,'四人项目组\n［成员 A］  ［成员 B］  ［成员 C］  ［成员 D］',21,C.mint);
 await img(s,'wave',852,172,330,400);
 const n=notes.find(x=>x.slide===22);if(n)s.speakerNotes.text=n.notes+'\n资料依据：'+n.sources.join('\n');
}
// 23 appendix evidence
{
 const s=slide('实验指标与训练参数','备用页  A');
 table(s,64,181,1152,222,[['分类评估集合','图像数','Top-1','宏平均 F1'],['验证集','5,485','99.7265%','99.5417%'],['独立测试集','10,999','99.6727%','99.5620%']], [350,210,296,296],24);
 text(s,64,440,1140,91,'训练：224 × 224，batch 32，AdamW，lr 0.0005，AMP，40 轮\n最佳模型由验证集选择，分类 ONNX 最大绝对误差为 2.98 × 10⁻⁷',24,C.ink);
 text(s,64,566,1150,70,'新目标检测模型：640 × 640，阈值 0.25，38 类\n五张技术样例仅验证导出一致性，尚无独立检测集 mAP',24,C.green,true);
}
// 24 appendix questions
{
 const s=slide('答辩问答参考','备用页  B');
 lineItem(s,'Q1','99.67% 代表什么？','它是 PlantVillage 独立测试集的单叶分类 Top-1，不能代表田间准确率或检测 mAP。',182);
 lineItem(s,'Q2','目标框能算严重度吗？','当前框表示模型检测目标，缺少病斑精确轮廓。严重度估计需要专门标注与分割评估。',327);
 lineItem(s,'Q3','系统如何避免假结果？','模型结果与 AI 解读分开保存。\n无可靠目标或服务失败时明确提示，保留重试入口。',472);
}

await fs.mkdir(path.join(BUILD,'previews'),{recursive:true});
await fs.writeFile(path.join(BUILD,'slides-text.json'),JSON.stringify(allTexts,null,2));
await fs.writeFile(path.join(BUILD,'presentation.json'),JSON.stringify(p.toProto()));
const draft=path.join(BUILD,'draft.pptx');
await(await PresentationFile.exportPptx(p)).save(draft);console.log('Draft:',draft);
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(BUILD,'previews',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
 console.log('Rendered',i+1);
}
const tiles=[];for(let i=1;i<=24;i++){const b=await sharp(path.join(BUILD,'previews',`slide-${String(i).padStart(2,'0')}.png`)).resize(320,180).png().toBuffer();tiles.push({input:b,left:((i-1)%4)*320,top:Math.floor((i-1)/4)*180});}
await sharp({create:{width:1280,height:1080,channels:3,background:'#D9E1D4'}}).composite(tiles).png().toFile(path.join(BUILD,'contact-sheet.png'));
if(process.env.SKIP_FINALIZE!=='1'){
 const final=path.join(OUT,'禾观AgriScan_课程答辩_24页.pptx');
 const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:draft,finalPath:final,pythonExecutable:PY,integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:24,requiredNativeTableOwnerSlides:[7,9,11,23],requiredNativeChartOwnerSlides:[6,10],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
 console.log(JSON.stringify(result));
}
