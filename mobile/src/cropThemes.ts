export const cropThemes: Record<string,{id:string;accent:string;dark:string;soft:string;canvas:string}> = {
  '番茄':{id:'tomato',accent:'#a04e40',dark:'#713c31',soft:'#f5e9df',canvas:'#fbf8f1'},
  '苹果':{id:'apple',accent:'#a14c57',dark:'#713743',soft:'#f5e7e9',canvas:'#fbf7f3'},
  '蓝莓':{id:'blueberry',accent:'#5e70a0',dark:'#435475',soft:'#e9edf6',canvas:'#f7f8fb'},
  '樱桃':{id:'cherry',accent:'#a04d66',dark:'#71364b',soft:'#f5e5eb',canvas:'#fcf7f8'},
  '玉米':{id:'corn',accent:'#947431',dark:'#665321',soft:'#f6edd8',canvas:'#fcfaf2'},
  '葡萄':{id:'grape',accent:'#80609b',dark:'#5b4270',soft:'#f0e8f6',canvas:'#faf7fc'},
  '柑橘':{id:'citrus',accent:'#a06b32',dark:'#755026',soft:'#f8eddb',canvas:'#fffbf4'},
  '桃':{id:'peach',accent:'#a36763',dark:'#754b4a',soft:'#f8e8e2',canvas:'#fff9f5'},
  '甜椒':{id:'pepper',accent:'#5d7e44',dark:'#425b32',soft:'#edf3df',canvas:'#f8faf3'},
  '马铃薯':{id:'potato',accent:'#917354',dark:'#66513d',soft:'#f2eadd',canvas:'#fbf8f2'},
  '树莓':{id:'raspberry',accent:'#a0557a',dark:'#713b59',soft:'#f7e8f0',canvas:'#fcf7fa'},
  '大豆':{id:'soybean',accent:'#74874d',dark:'#515f36',soft:'#edf3df',canvas:'#f9fbf3'},
  '南瓜':{id:'pumpkin',accent:'#a87542',dark:'#75522f',soft:'#f8ecdc',canvas:'#fdf9f2'},
  '草莓':{id:'strawberry',accent:'#a3566c',dark:'#773e50',soft:'#f8e7ed',canvas:'#fff8fa'},
  '水稻':{id:'rice',accent:'#6a834b',dark:'#495b33',soft:'#eef3e2',canvas:'#f8faf2'},
  '小麦':{id:'wheat',accent:'#987b4b',dark:'#6a5635',soft:'#f6eddc',canvas:'#fbf9f2'},
  '黄瓜':{id:'cucumber',accent:'#528263',dark:'#395d47',soft:'#e7f1e4',canvas:'#f6faf3'},
}
export function applyCropTheme(crop:string) {
  const theme=cropThemes[crop];if(!theme)return
  document.documentElement.dataset.crop=theme.id
  for(const [key,value] of Object.entries({green:theme.accent,dark:theme.dark,soft:theme.soft,cream:theme.canvas}))document.documentElement.style.setProperty(`--${key}`,value)
  localStorage.setItem('agriscan-mobile-crop',crop)
}
