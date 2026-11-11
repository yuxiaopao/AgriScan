import fs from 'node:fs/promises';
const dir='E:/AgriScan/deliverables/defense/整套24页图片_20261029';
const first=JSON.parse(await fs.readFile('E:/AgriScan/deliverables/defense/图片方案_20261029/生成提示词.json','utf8'));
const fresh=JSON.parse(await fs.readFile(dir+'/新增20页完整生成记录.json','utf8'));
const mapping={cover:{n:1,title:'封面'},dataset:{n:5,title:'项目与数据集'},process:{n:8,title:'技术实现路线'},results:{n:14,title:'实验结果与系统成果'}};
const images=first.images.map(x=>({...mapping[x.key],path:dir+'/'+String(mapping[x.key].n).padStart(2,'0')+'_'+mapping[x.key].title+'.png',prompt:x.prompt})).concat(fresh.images).sort((a,b)=>a.n-b.n);
if(images.length!==24||images.some((x,i)=>x.n!==i+1))throw new Error('Incomplete image prompt set');
await fs.writeFile(dir+'/生成提示词_全部24页.json',JSON.stringify({method:'built-in image_gen',date:'2026-10-29',title:'禾观AgriScan课程答辩完整24页图片',image_count:24,images,local_revisions:fresh.local_revisions},null,2));
console.log('All 24 prompts recorded');
