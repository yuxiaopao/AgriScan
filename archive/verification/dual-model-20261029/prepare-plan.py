import json
from pathlib import Path
folder=Path('.runtime/dual-model-20261029')
package=json.loads((folder/'package.json').read_text(encoding='utf-8'))
baseline=json.loads((folder/'runtime-preswitch-final.json').read_text(encoding='utf-8'))
classification=json.loads((folder/'classification-package.json').read_text(encoding='utf-8'))
apk=json.loads(Path('.runtime/mobile-auth-final-20261029/apk/verification.json').read_text(encoding='utf-8'))
plan=json.loads((folder/'deployment-plan.example.json').read_text(encoding='utf-8'))
plan.update(patch_archive_path='/srv/agriscan/bootstrap/dual-model-update-20261029.tar.gz',
            patch_sha256=package['sha256'],release_id=package['release_id'],
            payload_manifest_sha256=package['payload_manifest_sha256'],
            expected_current=baseline['release'],expected_schema=baseline['schema'],
            expected_configuration_version=baseline['configuration']['version'],
            expected_configuration_sha256=baseline['configuration']['row_sha256'],
            expected_api_pid=int(baseline['api']['MainPID']),
            classification_archive_sha256=classification['sha256'],
            classification_onnx_sha256=classification['model_onnx_sha256'],
            apk_sha256=apk['sha256'],apk_bytes=apk['apk_bytes'],
            apk_version=apk['version'],apk_version_code=apk['version_code'])
(folder/'deployment-plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
print(json.dumps({'status':'prepared','release_id':plan['release_id'],'patch_sha256':plan['patch_sha256']}))
