import {USERNAME_ERROR} from './accountValidation'

const fieldNames: Record<string, string> = {
  username: '用户名', name: '昵称', email: '邮箱', password: '密码', new_password: '新密码',
  current_password: '当前密码', code: '邮箱验证码', confirm: '确认密码',
}

function validationMessage(value: unknown): string {
  if (!value || typeof value !== 'object') return '填写内容不符合要求，请检查后重试。'
  const item = value as {loc?: unknown; type?: unknown; msg?: unknown; ctx?: unknown}
  const location = Array.isArray(item.loc) ? item.loc : []
  const field = [...location].reverse().find(part => typeof part === 'string' && Object.hasOwn(fieldNames, part))
  const label = typeof field === 'string' ? fieldNames[field] : '填写内容'
  if (item.type === 'missing') return `请填写${label}。`
  if (field === 'username') return USERNAME_ERROR
  if (item.type === 'value_error' && typeof item.msg === 'string' && /[\u3400-\u9fff]/.test(item.msg)) return item.msg.replace(/^Value error,\s*/, '')
  const context = item.ctx && typeof item.ctx === 'object' ? item.ctx as Record<string, unknown> : {}
  const limit = item.type === 'string_too_short' ? context.min_length : context.max_length
  if (typeof limit === 'number' && Number.isSafeInteger(limit) && limit > 0 && limit <= 1_000_000) {
    if (item.type === 'string_too_short') return `${label}至少需要 ${limit} 个字符。`
    if (item.type === 'string_too_long') return `${label}不能超过 ${limit} 个字符。`
  }
  if (field === 'email') return '请填写有效的邮箱地址。'
  if (field === 'code') return '请填写邮件中的 6 位数字验证码。'
  return `${label}格式不正确，请检查后重试。`
}

// Never render Pydantic input, context patterns, or technical English messages.
export function apiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail
  if (!Array.isArray(detail) || !detail.length) return fallback
  return [...new Set(detail.slice(0, 3).map(validationMessage))].join('；')
}
