from pathlib import Path
import json
import re
from zipfile import ZipFile

apk = Path('mobile/android/app/build/outputs/apk/debug/app-debug.apk')
with ZipFile(apk) as archive:
    assert archive.testzip() is None, 'APK ZIP CRC verification failed'
    config = json.loads(archive.read('assets/capacitor.config.json'))
    assert config['appId'] == 'cn.agriscan.mobile'
    assert config['server']['androidScheme'] == 'https'
    assert config['android']['allowMixedContent'] is False
    bundles = [name for name in archive.namelist() if re.fullmatch(r'assets/public/assets/index-[^/]+\.js', name)]
    assert len(bundles) == 1
    text = archive.read(bundles[0]).decode('utf8')
    compiled = re.search(r'\w+="agriscan-mobile-service",\w+="([^"]+)",\w+="([^"]+)",\w+="([^"]+)";function ', text)
    assert compiled, 'Cannot identify compiled service configuration'
    default, previous, official = compiled.groups()
    assert default == official == 'https://agriscan.ming-ai.top/agriscan'
    assert previous == 'https://flowly-ai.top/agriscan'
    report = {'zipCrcVerified': True, 'capacitorConfig': config, 'javascriptBundle': bundles[0],
              'compiledDefault': default, 'migrationPreviousOrigin': previous,
              'officialMigrationTarget': official, 'oldOriginOnlyForExplicitMigration': True,
              'appRuntimeOpened': False, 'hardwareTested': False}
Path('.runtime/domain-migration-20261029/zip-inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps({'zipVerified': True, 'compiledDefault': default, 'capacitorMixedContent': False}))
