from pathlib import Path

admin = Path('admin/src/Admin.tsx')
text = admin.read_text(encoding='utf-8')
text = text.replace("import './admin.css'", "import './admin.css'\nimport {registrationUsernameError, USERNAME_HELP, USERNAME_MAX_LENGTH} from '../../shared/accountValidation'")
before = "async function submit(event: FormEvent) {event.preventDefault(); setBusy(true); setError(''); try {const body = row ? {name: name.trim(), email: email.trim(),"
after = "async function submit(event: FormEvent) {event.preventDefault(); setError(''); if(!row){const invalidUsername=registrationUsernameError(username.trim());if(invalidUsername){setError(invalidUsername);return}} setBusy(true); try {const body = row ? {name: name.trim(), email: email.trim(),"
assert text.count(before) == 1
text = text.replace(before, after)
before = '<input required maxLength={40} minLength={3} pattern="[a-zA-Z0-9_-]+" title="3–40位英文字母、数字、下划线或短横线" autoComplete="off" value={username}'
after = '<input required maxLength={USERNAME_MAX_LENGTH} minLength={3} title={USERNAME_HELP} placeholder="用户名或邮箱地址" autoComplete="off" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={username}'
assert text.count(before) == 1
text = text.replace(before, after)
admin.write_text(text, encoding='utf-8', newline='')
