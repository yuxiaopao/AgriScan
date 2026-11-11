"""Schema regression probe only: no OTP requests, email, or account creation."""
import argparse
import json
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--expect-fixed', action='store_true')
args = parser.parse_args()
results = []
for username in ('qa_registration_probe', 'qa.registration.probe@example.invalid'):
    body = {'username': username, 'name': 'Registration probe',
            'password': 'REDACTED_SECRET',
            'email': 'qa.registration.probe@example.invalid', 'code': '000000'}
    request = urllib.request.Request(
        'https://agriscan.ming-ai.top/agriscan/api/auth/register',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, data = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, data = error.code, json.load(error)
    results.append({'kind': 'email' if '@' in username else 'ordinary',
                    'status': status, 'detail': data.get('detail')})
print(json.dumps(results, ensure_ascii=False, indent=2))
if args.expect_fixed:
    assert all(item['status'] == 400 and isinstance(item['detail'], str)
               and '验证码' in item['detail'] for item in results), results
else:
    assert results[1]['status'] == 422 and isinstance(results[1]['detail'], list), results
    assert any(item.get('type') == 'string_pattern_mismatch'
               for item in results[1]['detail']), results
