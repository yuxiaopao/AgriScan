import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
import sharp from 'sharp';
const build='E:/AgriScan/.runtime/defense-ppt-build';
const presentation=await PresentationFile.importPptx(await FileBlob.load('E:/AgriScan/deliverables/defense/禾观AgriScan_课程答辩_24页.pptx'));
const dir=path.join(build,'final-previews');await fs.mkdir(dir,{recursive:true});
let same=0;
for(let i=0;i<presentation.slides.items.length;i++){
 const blob=await presentation.export({slide:presentation.slides.items[i],format:'png',scale:1});
 const name=`slide-${String(i+1).padStart(2,'0')}.png`;
 const bytes=new Uint8Array(await blob.arrayBuffer());await fs.writeFile(path.join(dir,name),bytes);
 const old=await sharp(path.join(build,'previews',name)).raw().toBuffer();
 const now=await sharp(bytes).raw().toBuffer();
 if(old.equals(now))same++;
}
console.log(JSON.stringify({slides:presentation.slides.items.length,pixelIdenticalToReviewedDraft:same,output:dir}));
