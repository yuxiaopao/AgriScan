import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
const root='E:/AgriScan', out=path.join(root,'.runtime/defense-ppt-build/assets');
await fs.mkdir(out,{recursive:true});
for(const [name,src] of Object.entries({mascot:'frontend/public/images/xiaohe.png',wave:'design/xiaohe-motion/frames/wave/00.png',think:'design/xiaohe-motion/frames/think/00.png',success:'design/xiaohe-motion/frames/success/00.png',concern:'design/xiaohe-motion/frames/concern/00.png'})){
 await sharp(path.join(root,src)).trim().resize({height:1100,withoutEnlargement:true}).png().toFile(path.join(out,name+'.png'));
}
for(const name of ['apple','corn','tomato','grape','potato','citrus']) await sharp(path.join(root,`frontend/public/images/xiaohe-crops/${name}-still.webp`)).trim().png().toFile(path.join(out,name+'.png'));
await sharp(path.join(root,'frontend/public/brand/logo.svg')).resize({width:600}).png().toFile(path.join(out,'logo.png'));
await sharp(path.join(root,'design/qa-20261028/production-apple-yolo.png')).extract({left:280,top:515,width:945,height:617}).png().toFile(path.join(out,'detect-result.png'));
const desktopMeta=await sharp(path.join(root,'design/dashboard-desktop.png')).metadata();
await sharp(path.join(root,'design/dashboard-desktop.png')).extract({left:0,top:0,width:desktopMeta.width,height:1000}).resize(1152).png().toFile(path.join(out,'desktop.png'));
await sharp(path.join(root,'design/app-preview/home.png')).png().toFile(path.join(out,'mobile-home.png'));
await sharp(path.join(root,'design/admin-workspace-20261028.png')).png().toFile(path.join(out,'admin.png'));
await sharp(path.join(root,'design/app-preview/image-result.png')).extract({left:0,top:1030,width:374,height:930}).png().toFile(path.join(out,'mobile-result.png'));
const samples=[['Apple___Apple_scab','苹果黑星病'],['Apple___healthy','苹果健康'],['Corn_(maize)___Common_rust_','玉米普通锈病'],['Tomato___Early_blight','番茄早疫病']];
const sampleMeta=[];
for(let i=0;i<samples.length;i++){
 const [dir,label]=samples[i], folder=path.join(root,'datasets/plantvillage/classification/test',dir);
 const f=(await fs.readdir(folder)).find(x=>/\.(jpg|jpeg|png)$/i.test(x));
 const src=path.join(folder,f), dest=path.join(out,`leaf${i}.png`);
 await sharp(src).resize(400,400,{fit:'contain',background:'#F8F8F2'}).png().toFile(dest);
 sampleMeta.push({label,source:src,file:dest});
}
await fs.writeFile(path.join(out,'samples.json'),JSON.stringify(sampleMeta,null,2));
console.log('Assets prepared:',out);
