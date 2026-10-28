const toggle=document.querySelector('.menu-toggle'),navigation=document.querySelector('#navigation');
function setMenu(open){toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'关闭导航':'打开导航');navigation.classList.toggle('open',open)}
toggle.addEventListener('click',()=>setMenu(toggle.getAttribute('aria-expanded')!=='true'));
navigation.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>setMenu(false)));
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&toggle.getAttribute('aria-expanded')==='true'){setMenu(false);toggle.focus()}});
document.querySelector('#year').textContent=String(new Date().getFullYear());
if(['localhost','127.0.0.1'].includes(location.hostname)&&location.port==='5177'){
  document.querySelectorAll('.workspace-link').forEach(link=>link.href=`http://${location.hostname}:5173/${link.hash||'#login'}`);
  document.querySelector('.admin-link').href=`http://${location.hostname}:5175/`;
}
async function loadRelease(){
  const button=document.querySelector('#apk-download'),note=document.querySelector('#download-note');
  try{
    const response=await fetch('./downloads/release.json',{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!response.ok)throw new Error();
    const release=await response.json();
    if(release.status!=='ready'){document.querySelector('#release-info').textContent='Android 7.0+ · 安装包准备中';note.textContent='安装包尚未发布，请稍后重新检查。';return}
    const url=new URL(release.url,location.href),base=new URL('./downloads/',location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith(base.pathname)||!url.pathname.endsWith('.apk')||!/^[a-f0-9]{64}$/i.test(release.sha256))throw new Error();
    button.href=url.href;button.download=url.pathname.split('/').pop();button.removeAttribute('aria-disabled');button.innerHTML='下载 Android APK <span aria-hidden="true">↓</span>';
    document.querySelector('#release-info').textContent=`v${release.version} · ${release.channel||'公开测试版'} · ${(release.size_bytes/1024/1024).toFixed(1)} MB`;
    document.querySelector('#apk-sha').textContent=`SHA-256: ${release.sha256}`;note.textContent='当前为测试安装包；下载后按手机系统提示安装。';
  }catch{document.querySelector('#release-info').textContent='暂时无法读取安装包信息';note.textContent='请检查网络，或点击下方“重新检查下载”。'}
}
document.querySelector('#release-retry').addEventListener('click',loadRelease);loadRelease();
