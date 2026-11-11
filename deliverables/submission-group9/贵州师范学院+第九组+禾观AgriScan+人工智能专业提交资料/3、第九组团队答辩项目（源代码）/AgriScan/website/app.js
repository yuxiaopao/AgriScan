const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
const mobileQuery = window.matchMedia('(max-width: 740px)');
const curve = 'cubic-bezier(.22,1,.36,1)';
const toggle = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
const main = document.querySelector('main');
const footer = document.querySelector('.footer');

function arrive(element, distance = 12) {
  if (!element?.animate) return;
  element.getAnimations().forEach(animation => animation.cancel());
  element.animate(motionQuery.matches ? [{ opacity: .45 }, { opacity: 1 }] : [
    { opacity: 0, transform: `translateY(${distance}px)` },
    { opacity: 1, transform: 'translateY(0)' },
  ], { duration: motionQuery.matches ? 200 : 500, easing: curve });
}

function setMenu(open, restoreFocus = false) {
  const isOpen = open && mobileQuery.matches;
  toggle.setAttribute('aria-expanded', String(isOpen));
  toggle.setAttribute('aria-label', isOpen ? '关闭导航' : '打开导航');
  navigation.classList.toggle('open', isOpen);
  navigation.inert = mobileQuery.matches && !isOpen;
  main.inert = isOpen;
  footer.inert = isOpen;
  document.body.classList.toggle('menu-open', isOpen);
  if (restoreFocus) toggle.focus();
}

toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMenu(false, mobileQuery.matches)));
mobileQuery.addEventListener('change', () => setMenu(false));
setMenu(false);
document.addEventListener('keydown', event => {
  if (toggle.getAttribute('aria-expanded') !== 'true') return;
  if (event.key === 'Escape') { setMenu(false, true); return; }
  if (event.key !== 'Tab') return;
  const focusable = [...document.querySelectorAll('.header a, .header button')].filter(element => !element.closest('[inert]') && element.getClientRects().length);
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

document.querySelector('#year').textContent = String(new Date().getFullYear());
if (['localhost', '127.0.0.1'].includes(location.hostname) && location.port === '5177') {
  document.querySelectorAll('.workspace-link').forEach(link => { link.href = `http://${location.hostname}:5173/${link.hash || '#login'}`; });
  document.querySelector('.admin-link').href = `http://${location.hostname}:5175/`;
}

if ('IntersectionObserver' in window && !motionQuery.matches) {
  document.documentElement.classList.add('motion-ready');
  const reveal = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('is-visible'); reveal.unobserve(entry.target); }
  }), { threshold: .08, rootMargin: '0px 0px -24px 0px' });
  document.querySelectorAll('[data-reveal]').forEach(element => reveal.observe(element));
  const words = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('is-visible'); words.unobserve(entry.target); }
  }), { rootMargin: '0px 0px -30% 0px', threshold: 1 });
  document.querySelectorAll('[data-word]').forEach(phrase => {
    const copy = phrase.textContent;
    const segments = typeof Intl.Segmenter === 'function'
      ? [...new Intl.Segmenter('zh-CN', { granularity: 'word' }).segment(copy)].map(item => item.segment)
      : Array.from(copy);
    phrase.removeAttribute('data-word');
    phrase.replaceChildren();
    segments.forEach((segment, index) => {
      const word = document.createElement('span');
      word.dataset.word = '';
      word.textContent = segment;
      word.style.transitionDelay = `${Math.min(index * 45, 300)}ms`;
      phrase.append(word);
      words.observe(word);
    });
  });
  motionQuery.addEventListener('change', event => {
    if (event.matches) {
      document.documentElement.classList.remove('motion-ready');
      document.querySelectorAll('[data-word]').forEach(word => word.classList.add('is-visible'));
      reveal.disconnect(); words.disconnect();
    }
  });
} else document.querySelectorAll('[data-word]').forEach(word => word.classList.add('is-visible'));

if ('IntersectionObserver' in window) {
  const sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      navigation.querySelectorAll('a').forEach(link => {
        if (link.hash === `#${entry.target.id}`) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    });
  }, { rootMargin: '-18% 0px -50% 0px', threshold: 0 });
  document.querySelectorAll('#observe, #app, #workspace, #help').forEach(section => sectionObserver.observe(section));
}

document.querySelectorAll('.feature-toggle').forEach(button => {
  button.addEventListener('click', () => {
    const panel = document.getElementById(button.getAttribute('aria-controls'));
    const open = button.getAttribute('aria-expanded') !== 'true';
    const cards = [...document.querySelectorAll('.feature')];
    const positions = cards.map(card => card.getBoundingClientRect());
    document.querySelectorAll('.feature-toggle').forEach(other => {
      const detail = document.getElementById(other.getAttribute('aria-controls'));
      const expanded = other === button && open;
      other.setAttribute('aria-expanded', String(expanded));
      other.closest('.feature').classList.toggle('is-expanded', expanded);
      detail.hidden = !expanded;
    });
    // FLIP keeps neighbouring mobile cards connected as a detail card unfolds.
    if (!motionQuery.matches) cards.forEach((card, index) => {
      const delta = positions[index].top - card.getBoundingClientRect().top;
      if (Math.abs(delta) > 1 && card.animate) card.animate([{ transform: `translateY(${delta}px)` }, { transform: 'translateY(0)' }], { duration: 500, easing: curve });
    });
    if (open) arrive(panel, 16);
  });
});

const workflowDetails = [
  ['从画面里，找到线索', '原图、目标框和识别结果一起查看，先核对画面，再结合现场情况判断。'],
  ['把发现，放回田间', '关联对应地块，补充采样备注，让每次记录都能回答在哪里、看到了什么。'],
  ['下一次观察，从这里继续', '回看历史记录，核对前后的变化；需要进一步讨论时，把观察交给小禾。'],
];
document.querySelectorAll('.workflow-step').forEach(button => button.addEventListener('click', () => {
  const selected = Number(button.dataset.step);
  if (button.getAttribute('aria-pressed') === 'true') return;
  document.querySelectorAll('.workflow-step').forEach(step => {
    const active = step === button;
    step.setAttribute('aria-pressed', String(active));
    step.classList.toggle('is-active', active);
  });
  document.querySelector('.workflow-rail>span').style.transform = `scaleY(${selected / 2})`;
  const detail = document.querySelector('#workflow-detail');
  detail.querySelector('.detail-label').textContent = workflowDetails[selected][0];
  detail.querySelector('p').textContent = workflowDetails[selected][1];
  arrive(detail);
}));

document.querySelectorAll('details').forEach(details => details.addEventListener('toggle', () => {
  if (details.open) arrive(details.querySelector('p') || details.querySelector('div'));
}));

const downloadButton = document.querySelector('#apk-download');
const downloadNote = document.querySelector('#download-note');
const retryButton = document.querySelector('#release-retry');
const downloadCard = document.querySelector('.download-card');
let releaseLoading = false;
let downloadReset;

function setDownloadLabel(label) {
  downloadButton.textContent = label;
}

async function loadRelease() {
  if (releaseLoading) return;
  releaseLoading = true;
  retryButton.disabled = true;
  retryButton.textContent = '正在检查版本…';
  retryButton.setAttribute('aria-busy', 'true');
  downloadCard.classList.remove('is-error');
  clearTimeout(downloadReset);
  // A withdrawn or failed release must not leave an old download enabled.
  downloadButton.removeAttribute('href');
  downloadButton.removeAttribute('download');
  downloadButton.setAttribute('aria-disabled', 'true');
  downloadCard.classList.remove('is-ready');
  document.querySelector('#apk-sha').textContent = '暂无安装包校验值';
  setDownloadLabel('正在检查安装包');
  try {
    const response = await fetch('./downloads/release.json', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('release unavailable');
    const release = await response.json();
    if (release.status !== 'ready') {
      document.querySelector('#release-info').textContent = 'Android 7.0+ · 安装包准备中';
      downloadNote.textContent = '安装包尚未发布，请稍后重新检查。';
      setDownloadLabel('安装包准备中');
      return;
    }
    const url = new URL(release.url, location.href), base = new URL('./downloads/', location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith(base.pathname) || !url.pathname.endsWith('.apk') || !/^[a-f0-9]{64}$/i.test(release.sha256) || !Number.isFinite(release.size_bytes) || release.size_bytes <= 0 || typeof release.version !== 'string') throw new Error('invalid release');
    downloadButton.href = url.href;
    downloadButton.download = url.pathname.split('/').pop();
    downloadButton.removeAttribute('aria-disabled');
    setDownloadLabel('下载 Android APK');
    downloadCard.classList.add('is-ready');
    document.querySelector('#release-info').textContent = `v${release.version} · ${release.channel || '公开测试版'} · ${(release.size_bytes / 1024 / 1024).toFixed(1)} MB`;
    document.querySelector('#apk-sha').textContent = `SHA256: ${release.sha256}`;
    downloadNote.textContent = '当前为测试安装包；下载后按手机系统提示安装。';
    arrive(downloadButton, 4);
  } catch {
    downloadCard.classList.add('is-error');
    document.querySelector('#release-info').textContent = '暂时无法读取安装包信息';
    downloadNote.textContent = '请检查网络，展开下方版本信息后重新检查。';
    setDownloadLabel('暂时无法获取安装包');
  } finally {
    releaseLoading = false;
    retryButton.disabled = false;
    retryButton.removeAttribute('aria-busy');
    retryButton.textContent = '重新检查下载';
  }
}

downloadButton.addEventListener('click', event => {
  if (downloadButton.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
  clearTimeout(downloadReset);
  setDownloadLabel('下载请求已发出');
  downloadButton.classList.add('is-requested');
  downloadNote.textContent = '请在浏览器的下载列表查看进度。下载完成后，按手机系统提示安装。';
  arrive(downloadButton, 4);
  downloadReset = setTimeout(() => {
    setDownloadLabel('再次下载 Android APK');
    downloadButton.classList.remove('is-requested');
  }, 5000);
});
retryButton.addEventListener('click', loadRelease);
loadRelease();
