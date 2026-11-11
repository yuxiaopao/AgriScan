from pathlib import Path
import re

root = Path('E:/AgriScan/website')
p = root / 'index.html'
s = p.read_text(encoding='utf-8')
# Direction glyphs on ordinary links add no information; preserve disclosure controls.
s = re.sub(r'\s*<span(?: class="step-arrow")? aria-hidden="true">[↗↓→↘↑]</span>', '', s)
s = s.replace(' ↗', '').replace(' ↓', '')
s = s.replace('YOUR LITTLE FIELD COMPANION', '禾观 · 作物健康工作空间')
s = s.replace('A CLOSER LOOK', '从观察开始')
s = s.replace('SMALL OBSERVATIONS, LASTING RECORDS', '小小观察，长久记录')
s = s.replace('TAKE XIAOHE WITH YOU', '把田间助手带在身边')
s = s.replace('YOUR FIELD, IN ONE PLACE', '回到熟悉的工作空间')
s = s.replace('EVERY OBSERVATION MATTERS', '每一次发现，都有迹可循')
s = s.replace('A LITTLE HELP', '陪你开始')
s = s.replace('GROW A LITTLE CLOSER', '从一片叶子，慢慢了解田野')
s = s.replace('01 / PHOTO', '01 · 图片观察').replace('02 / LIVE CAMERA', '02 · 实时相机').replace('03 / VIDEO', '03 · 视频记录')
s = s.replace('<h1>每一片叶子，<br>都值得认真看见。</h1>', '<h1><span class="hero-title-line">每一片叶子，</span><span class="hero-title-line">都值得认真看见。</span></h1>')
s = s.replace('<p>从一张叶片照片，到一次田间巡查。<br>和小禾一起，记录作物的变化，让照顾更有依据。</p>', '<p class="hero-description"><span>从一张叶片照片，到一次田间巡查。</span><span>和小禾一起，把每一次发现留进田间档案。</span></p>')
s = s.replace('往下认识我们', '继续认识禾观')
s = s.replace('下载手机 APP', '下载手机应用').replace('手机 APP', '手机应用').replace('Android APP', 'Android 应用')
s = s.replace('也可以直接打开网页版', '打开网页版，继续田间观察')
p.write_text(s, encoding='utf-8')

p = root / 'app.js'
s = p.read_text(encoding='utf-8')
s = s.replace("function setDownloadLabel(label, symbol) {\n  downloadButton.replaceChildren(document.createTextNode(label));\n  const icon = document.createElement('span');\n  icon.setAttribute('aria-hidden', 'true');\n  icon.textContent = symbol;\n  downloadButton.append(icon);\n}", "function setDownloadLabel(label) {\n  downloadButton.textContent = label;\n}")
s = re.sub(r"setDownloadLabel\((('[^']*')|(`[^`]*`)), '[↓✓]'\)", r'setDownloadLabel(\1)', s)
s = s.replace("arrive(downloadButton.querySelector('span'), 8);", 'arrive(downloadButton, 4);')
p.write_text(s, encoding='utf-8')

p = root / 'style.css'
s = p.read_text(encoding='utf-8')
s += '''
/* Quiet typography: purposeful Chinese copy, softer hierarchy, simple action labels. */
:root{--ink:#263d30;--muted:#5f735e;--subtle:#73856c}
body{font-family:Geist,"PingFang SC","Microsoft YaHei",sans-serif;font-size:16px;line-height:24px;letter-spacing:.01em;font-synthesis:none}
h1,h2,h3{font-weight:500;letter-spacing:-.025em}h1{font-weight:500;line-height:1;margin:24px 0 32px}.hero-title-line{display:block;white-space:nowrap}.hero-title-line+.hero-title-line{margin-top:12px}
.eyebrow{font-size:12px;line-height:16px;font-weight:500;letter-spacing:.12em;color:var(--subtle)}
.hero-copy>.eyebrow{font-size:12px;line-height:16px;letter-spacing:.12em;gap:8px}.hero-copy>.eyebrow i{width:6px;height:6px}
.hero-copy>.hero-description{font-size:16px;line-height:24px;letter-spacing:.02em;max-width:560px;color:var(--muted)}.hero-description>span{display:block}.hero-description>span+span{margin-top:4px}
.actions{gap:24px;align-items:center;margin:32px 0 24px}.button{font-size:16px;line-height:24px;font-weight:600;padding:8px 24px;gap:0;min-height:48px;border-radius:12px;letter-spacing:.02em}.nav-login{font-size:14px;line-height:20px;font-weight:500;padding:12px 16px;border-radius:12px;letter-spacing:.02em}.header nav{font-size:14px;line-height:20px}.header nav>a{font-weight:400}.hero-web-link{font-size:14px;line-height:20px;font-weight:500;color:#4d6a51;padding:12px 0;box-shadow:0 1px 0 #bdcbb3}.hero-web-link:hover{color:var(--green);box-shadow:0 1px 0 var(--green)}
.hero-note{font-size:12px;line-height:16px;gap:12px;letter-spacing:.04em}.hero-bottom{font-size:12px;line-height:16px;color:var(--subtle)}.hero-bottom a{font-size:12px;line-height:16px;color:var(--muted)}.art-label{font-size:14px;line-height:20px;font-weight:400;letter-spacing:.01em}.art-caption>span{font-size:12px;line-height:16px;letter-spacing:.16em}.art-caption strong{font-size:12px;line-height:16px;font-weight:400;letter-spacing:.04em}
.section-heading>p,.app-copy>p,.workspace-copy>p,.help>div>p{font-size:16px;line-height:24px;color:var(--muted);letter-spacing:.015em}.section-heading>p{max-width:400px}.feature h3,.workflow-content>h3{font-weight:500;letter-spacing:-.01em}.feature>p,.feature-detail>p{font-size:14px;line-height:20px;letter-spacing:.015em}.feature-top{font-size:12px;line-height:16px;letter-spacing:.08em}.feature-toggle,.text-link{font-size:14px;line-height:20px;font-weight:500}.text-link{box-shadow:0 1px 0 #bdcbb3;padding-bottom:4px;gap:0}.method-note{font-size:12px;line-height:16px;max-width:800px}
.tagline-copy{font-weight:500;letter-spacing:-.025em}.tagline-note{font-size:14px;line-height:20px}.download-button{justify-content:center}.download-card strong{font-weight:500}.check-list{font-size:14px;line-height:20px;gap:16px}.workflow-step strong,.detail-label{font-weight:500}.workflow-step{padding-right:12px}.workflow-detail p{font-size:14px;line-height:20px}.workflow-footer{font-size:12px;line-height:16px}.faq summary{font-size:16px;line-height:24px;font-weight:500;letter-spacing:.01em}.faq details>p{font-size:14px;line-height:20px}.closing h2{font-weight:500}.closing-web{font-size:14px;line-height:20px;margin-top:16px}.footer>p,.footer>div{font-size:12px;line-height:16px}
@media(max-width:1000px){h1{font-size:36px;line-height:40px;letter-spacing:-.025em}.hero-title-line+.hero-title-line{margin-top:4px}.hero-copy>.hero-description{font-size:16px;line-height:24px}.actions{gap:24px}.feature h3{font-size:18px;line-height:28px}.feature>p{min-height:100px}.section-heading>p{max-width:360px}}
@media(max-width:740px){.header nav>a{font-size:30px;line-height:36px;font-weight:500}.nav-login{font-size:12px;line-height:16px;padding:8px 12px}.hero-copy>.eyebrow{font-size:12px;line-height:16px;letter-spacing:.08em}.hero-copy{padding:16px 0 0}h1{font-size:36px;line-height:40px;margin:24px 0}.hero-title-line+.hero-title-line{margin-top:4px}.hero-copy>.hero-description{font-size:16px;line-height:24px}.hero-description>span+span{margin-top:8px}.actions{gap:24px;margin:24px 0}.button{min-height:48px;padding:8px 24px;border-radius:12px}.hero-web-link{font-size:14px;line-height:20px}.art-label{font-size:12px;line-height:16px}.section-heading>p,.app-copy>p,.workspace-copy>p,.help>div>p{font-size:16px;line-height:24px}.feature h3{font-size:18px;line-height:28px}.feature>p{min-height:80px}.eyebrow,.tagline>.eyebrow,.closing .eyebrow{letter-spacing:.08em}.faq summary{font-size:14px;line-height:20px}.hero-bottom{gap:16px}.tagline-note{font-size:14px;line-height:20px}.closing h2{font-size:24px;line-height:32px}}
@media(max-width:380px){h1{font-size:30px;line-height:36px;letter-spacing:-.025em}.hero-title-line+.hero-title-line{margin-top:0}.hero-copy>.eyebrow{font-size:12px;letter-spacing:.04em}.hero-copy>.hero-description{font-size:14px;line-height:20px}.actions{gap:16px}.button{padding:8px 16px}.hero-web-link{font-size:14px}.hero-note{gap:8px;letter-spacing:0}.hero-bottom{gap:8px}.feature h3{font-size:16px;line-height:24px}}
'''
p.write_text(s, encoding='utf-8')
