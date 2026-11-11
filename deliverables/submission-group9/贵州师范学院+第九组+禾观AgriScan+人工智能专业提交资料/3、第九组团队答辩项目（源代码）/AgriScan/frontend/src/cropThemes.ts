export interface CropTheme {
  crop: string
  id: string
  icon: string
  name: string
  accent: string
  dark: string
  soft: string
  canvas: string
  glow: string
  tagline: string
}

export const cropThemes: CropTheme[] = [
  {crop: '番茄', id: 'tomato', icon: '🍅', name: '番茄红', accent: '#a63f36', dark: '#74352f', soft: '#f9e9e4', canvas: '#faf7f4', glow: '#f1c1a3', tagline: '从一片叶子的变化，守护每一颗饱满。'},
  {crop: '水稻', id: 'rice', icon: '🌾', name: '稻田青', accent: '#59713a', dark: '#3c5027', soft: '#edf2df', canvas: '#f7f9f2', glow: '#d9e2a1', tagline: '走近稻田，让每一次观察都有收获。'},
  {crop: '玉米', id: 'corn', icon: '🌽', name: '玉米金', accent: '#8b641c', dark: '#604814', soft: '#fbf0d1', canvas: '#fcf9f0', glow: '#f5d67f', tagline: '把日光的颜色，留在健康生长的田间。'},
  {crop: '小麦', id: 'wheat', icon: '🌾', name: '麦穗金', accent: '#8d693b', dark: '#604a2d', soft: '#f4ead8', canvas: '#faf8f2', glow: '#e8cb97', tagline: '细看麦叶的纹理，静待麦穗染成金黄。'},
  {crop: '黄瓜', id: 'cucumber', icon: '🥒', name: '黄瓜绿', accent: '#397852', dark: '#26573b', soft: '#e5f1e3', canvas: '#f5f9f2', glow: '#bddda8', tagline: '沿着藤蔓的绿意，发现叶片的小变化。'},
  {crop: '苹果', id: 'apple', icon: '🍎', name: '苹果绯', accent: '#a43c4d', dark: '#752b3b', soft: '#f8e7e9', canvas: '#fbf6f5', glow: '#f2b8b4', tagline: '一叶一果，记录果园里的每一份生长。'},
  {crop: '蓝莓', id: 'blueberry', icon: '🫐', name: '蓝莓蓝', accent: '#4d5f9c', dark: '#344372', soft: '#e9edf9', canvas: '#f6f7fc', glow: '#c2cbee', tagline: '细小的果实，也值得细致的照料。'},
  {crop: '樱桃', id: 'cherry', icon: '🍒', name: '樱桃绛', accent: '#993951', dark: '#702a3e', soft: '#f7e6ed', canvas: '#fcf6f8', glow: '#eeb5cb', tagline: '关注叶间细节，守候枝头的一抹鲜红。'},
  {crop: '葡萄', id: 'grape', icon: '🍇', name: '葡萄紫', accent: '#765199', dark: '#53386c', soft: '#efe7f7', canvas: '#f9f6fc', glow: '#d8bce9', tagline: '循着藤叶的线索，守护一串串期待。'},
  {crop: '柑橘', id: 'citrus', icon: '🍊', name: '柑橘橙', accent: '#9e5b20', dark: '#724018', soft: '#fff0de', canvas: '#fffbf4', glow: '#ffd195', tagline: '让清新的橘香，从健康的枝叶开始。'},
  {crop: '桃', id: 'peach', icon: '🍑', name: '蜜桃粉', accent: '#a05256', dark: '#763a42', soft: '#fbe9e5', canvas: '#fff8f5', glow: '#f4c0b3', tagline: '温柔观察每片桃叶，记录果园的日常。'},
  {crop: '甜椒', id: 'pepper', icon: '🫑', name: '甜椒翠', accent: '#4d7837', dark: '#375429', soft: '#eaf3df', canvas: '#f7faf2', glow: '#c5dda2', tagline: '看清每一处细节，让鲜活的颜色继续生长。'},
  {crop: '马铃薯', id: 'potato', icon: '🥔', name: '薯田棕', accent: '#866044', dark: '#604431', soft: '#f3e9dd', canvas: '#faf7f2', glow: '#e5c8a7', tagline: '从地上的叶片，了解田里的生长。'},
  {crop: '树莓', id: 'raspberry', icon: '●', name: '树莓玫', accent: '#a23e6c', dark: '#752a50', soft: '#f9e6f0', canvas: '#fcf6fa', glow: '#efb9d5', tagline: '在细微之处，发现果园需要的照料。'},
  {crop: '大豆', id: 'soybean', icon: '🫛', name: '豆荚青', accent: '#64783b', dark: '#45532a', soft: '#eef3df', canvas: '#f8faf3', glow: '#d5e2ad', tagline: '一株一叶，陪伴豆田走向饱满。'},
  {crop: '南瓜', id: 'pumpkin', icon: '🎃', name: '南瓜橙', accent: '#a45b29', dark: '#743e1e', soft: '#fbeada', canvas: '#fdf8f1', glow: '#f2c18d', tagline: '把田间的变化，记进丰收的日历。'},
  {crop: '草莓', id: 'strawberry', icon: '🍓', name: '草莓莓红', accent: '#a7405b', dark: '#772c42', soft: '#fbe6ec', canvas: '#fff7f9', glow: '#f5bacb', tagline: '从叶片到果实，认真对待每一份鲜甜。'},
]

export const getCropTheme = (crop: string) => cropThemes.find(theme => theme.crop === crop)
