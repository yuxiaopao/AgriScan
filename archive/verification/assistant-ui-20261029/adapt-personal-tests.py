import ast
from pathlib import Path

root=Path('backend/tests')
files={
 'test_plots.py':None,
 'test_inference.py':None,
 'test_detection_inference.py':None,
 'test_auto_crop_assistant.py':None,
 'test_media.py':{'test_video_samples_real_frames_uniformly_and_persists_snapshots'},
 'test_api.py':{'test_upload_persists_real_image_without_diagnosis_then_deletes',
                'test_uploaded_jpeg_applies_exif_orientation_before_stripping_metadata',
                'test_invalid_uploads_are_rejected','test_plot_crud_and_history_integrity',
                'test_seed_runs_only_once_even_after_records_deleted'},
}
for filename,selected in files.items():
    path=root/filename
    source=path.read_text(encoding='utf-8')
    tree=ast.parse(source)
    lines=source.splitlines(keepends=True)
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line.encode('utf-8')))
    data=source.encode('utf-8')
    replacements=[]
    helper='owned_demo_auth' if filename=='test_api.py' else 'auth'
    for function in tree.body:
        if not isinstance(function,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        if selected is not None and function.name not in selected:continue
        if function.name=='test_existing_schema_is_extended_without_altering_plot_columns':continue
        for node in ast.walk(function):
            if (filename=='test_api.py' and isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                and node.func.id=='auth'):
                start=offsets[node.func.lineno-1]+node.func.col_offset
                end=offsets[node.func.end_lineno-1]+node.func.end_col_offset
                replacements.append((start,end,b'owned_demo_auth'))
            if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='get'
                    and isinstance(node.func.value,ast.Name) and node.func.value.id in {'client','media_client'}):continue
            if any(keyword.arg=='headers' for keyword in node.keywords):continue
            if not node.args:continue
            arg=node.args[0]
            if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and any(arg.value.startswith(prefix) for prefix in ['/api/health','/api/models','/api/auth']):continue
            end=offsets[node.end_lineno-1]+node.end_col_offset-1
            replacements.append((end,end,f', headers={helper}({node.func.value.id})'.encode()))
    for start,end,replacement in sorted(replacements,reverse=True):data=data[:start]+replacement+data[end:]
    updated=data.decode('utf-8')
    if filename!='test_api.py':
        for node in ast.parse(updated).body:
            if isinstance(node,ast.ImportFrom) and node.module=='test_api':
                original=updated.splitlines()[node.lineno-1]
                if 'auth' in [alias.name for alias in node.names]:
                    replacement='from test_api import '+', '.join('owned_demo_auth as auth' if alias.name=='auth' else alias.name+((' as '+alias.asname) if alias.asname else '') for alias in node.names)
                    updated=updated.replace(original,replacement,1)
    ast.parse(updated)
    path.write_text(updated,encoding='utf-8')
    print(filename,len(replacements))
