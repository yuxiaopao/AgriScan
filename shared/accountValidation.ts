export const USERNAME_MAX_LENGTH = 80
export const USERNAME_HELP = '3 至 80 位，可使用字母、数字、下划线或短横线，也可使用邮箱地址。'
export const USERNAME_ERROR = '用户名需为 3–80 位字母、数字、下划线、短横线，或有效邮箱地址。'

// Username and verified recovery email remain separate account fields.
// Keep the same ASCII identifier contract as the server; do not change case.
export function registrationUsernameError(value: string): string {
  if (value.length < 3 || value.length > USERNAME_MAX_LENGTH) return USERNAME_ERROR
  if (/^[a-zA-Z0-9_-]+$/.test(value)) return ''
  const parts = value.split('@')
  if (parts.length !== 2) return USERNAME_ERROR
  const [local, domain] = parts
  if (!local || local.length > 64 || local.startsWith('.') || local.endsWith('.') || local.includes('..')
      || !/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)) return USERNAME_ERROR
  const labels = domain.split('.')
  if (labels.length < 2 || labels.some(label => label.length > 63 || !/^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$/.test(label))) return USERNAME_ERROR
  return ''
}
