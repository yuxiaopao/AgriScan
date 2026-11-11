from pathlib import Path

root = Path('E:/AgriScan')
script = (root/'.runtime/isolation-20261029/build-apk.ps1').read_text(encoding='utf-8')
script = (script.replace('.runtime/isolation-20261029/build/mobile','.runtime/server-latest-20261029/mobile')
          .replace('.runtime/isolation-20261029/apk','.runtime/server-latest-20261029/apk')
          .replace('agriscan-test-1.0.2-code3.apk','agriscan-test-1.0.3-code4.apk')
          .replace("version='1.0.2';version_code=3", "version='1.0.3';version_code=4"))
assert '.runtime/isolation-20261029' not in script
assert 'agriscan-test-1.0.3-code4.apk' in script
(root/'.runtime/server-latest-20261029/build-mobile.ps1').write_text(script,encoding='utf-8')
