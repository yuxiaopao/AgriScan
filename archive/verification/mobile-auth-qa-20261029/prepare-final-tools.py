from pathlib import Path
old=Path('E:/AgriScan/.runtime/mobile-final-20261029')
new=Path('E:/AgriScan/.runtime/mobile-auth-final-20261029')
assert not new.exists(),'Keep every previous APK and snapshot intact.'
new.mkdir()
for name in ('prepare-mobile.py','build-mobile.ps1','verify-mobile.py','check-signature.ps1'):
    value=(old/name).read_text(encoding='utf-8').replace('mobile-final-20261029','mobile-auth-final-20261029')
    if name=='verify-mobile.py':
        value=value.replace("'uploaded_bytes'):","'uploaded_bytes','forgot-password','password_reset_enabled','/auth/password-reset-code','/auth/password-reset','/auth/email/verification-code','/auth/email/verify','邮箱与密码找回'):")
        value=value.replace("'dual_model_verification_included':True,","'dual_model_verification_included':True,'password_reset_and_verified_email_binding_included':True,")
        value=value.replace("source_app = (snapshot/'src/App.tsx').read_text(encoding='utf-8')","security_source=(snapshot/'src/accountSecurity.ts').read_text(encoding='utf-8')\nassert 'route:window.location.hash' in security_source and \"'hashchange'\" in security_source\nassert 'getServiceBase()===identity.current.base' in security_source and 'getToken()===identity.current.token' in security_source\nassert \"'forgot-password'\" in (snapshot/'src/hooks.ts').read_text(encoding='utf-8')\nsource_app = (snapshot/'src/App.tsx').read_text(encoding='utf-8')")
    (new/name).write_text(value,encoding='utf-8')
print(str(new))
