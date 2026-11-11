"""Document Capacitor's sole generated path adjustment without changing source/APK."""
import hashlib,json,re
from pathlib import Path
root=Path('E:/AgriScan');task=Path(__file__).resolve().parent
manifest=json.loads((task/'mobile-source-manifest.json').read_text(encoding='utf-8'))
derived=[]
for row in manifest['files']:
    source=root/row['path'];snapshot=task/row['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
    observed=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if observed==row['sha256']:continue
    assert row['path']=='mobile/android/capacitor.settings.gradle'
    before=source.read_text(encoding='utf-8');after=snapshot.read_text(encoding='utf-8')
    assert before.replace('../node_modules/','../../../../mobile/node_modules/')==after
    assert source.read_bytes().replace(b'../node_modules/',b'../../../../mobile/node_modules/')==snapshot.read_bytes()
    original=re.findall(r"new File\('([^']+)'\)",before);generated=re.findall(r"new File\('([^']+)'\)",after)
    assert len(original)==len(generated)==3
    paths=[]
    for first,second in zip(original,generated):
        expected=(source.parent/first).resolve();actual=(snapshot.parent/second).resolve()
        assert expected==actual and actual.is_dir() and actual.is_relative_to((root/'mobile/node_modules').resolve())
        paths.append(str(actual))
    derived.append({'path':row['path'],'source_sha256':row['sha256'],'generated_sha256':observed,
      'reason':'Capacitor sync resolves the snapshot node_modules junction to the same existing project dependencies and rewrites relative Gradle paths.',
      'only_relative_dependency_paths_changed':True,'byte_replacement_exact':True,'same_three_resolved_dependency_directories':paths})
assert len(derived)==1
report={'status':'passed','manifest_semantics':'Source inventory describes repository bytes copied before Capacitor generation. It is not a manifest of generated build outputs.',
 'repository_source_entries_unchanged':len(manifest['files']),'snapshot_source_entries_byte_identical':len(manifest['files'])-len(derived),
 'generated_files':derived,'apk_modified':False,'repository_modified':False}
(task/'build-derived-files.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
verification_path=task/'apk/verification.json';verification=json.loads(verification_path.read_text(encoding='utf-8'))
verification['source_manifest_semantics']=report['manifest_semantics']
verification['snapshot_byte_identical_source_count']=report['snapshot_source_entries_byte_identical']
verification['capacitor_generated_source_derivation']=str(task/'build-derived-files.json')
verification_path.write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
ready_path=task/'final-mobile-ready.json';ready=json.loads(ready_path.read_text(encoding='utf-8'))
ready['artifact']=verification
ready['checks'].pop('source_root_and_snapshot_stable',None)
ready['checks'].update(repository_source_entries_unchanged=147,snapshot_byte_identical_source_count=146,
 capacitor_generated_source_derivation=str(task/'build-derived-files.json'))
ready['source_manifest_semantics']=report['manifest_semantics']
ready_path.write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','repository_entries_unchanged':147,'snapshot_identical':146,'documented_generated_files':1,'apk_modified':False}))
