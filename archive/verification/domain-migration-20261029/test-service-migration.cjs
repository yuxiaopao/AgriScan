const fs = require('node:fs')
const vm = require('node:vm')
const assert = require('node:assert/strict')
const ts = require('../../mobile/node_modules/typescript')
const source = fs.readFileSync('mobile/src/api.ts', 'utf8').replaceAll('import.meta.env.VITE_API_BASE_URL', 'globalThis.compiledBase')
const compiled = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}}).outputText
const oldBase = 'https://flowly-ai.top/agriscan'
const newBase = 'https://agriscan.ming-ai.top/agriscan'
const storageKey = 'agriscan-mobile-service'
const results = []
function client(defaultBase, saved, tokens = {}) {
  const storage = new Map(Object.entries(tokens))
  if (saved !== undefined) storage.set(storageKey, saved)
  const exports = {}
  vm.runInNewContext(compiled, {exports, compiledBase: defaultBase, localStorage: {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  }, URL})
  return {api: exports, storage}
}
function check(name, run) {run(); results.push({name, status: 'passed'})}
check('Exact saved official address migrates once', () => {
  const c = client(newBase, oldBase)
  assert.equal(c.api.getServiceBase(), newBase)
  assert.equal(c.storage.get(storageKey), newBase)
  assert.equal(c.api.getServiceBase(), newBase)
})
check('One trailing slash on previous official address migrates', () => {
  assert.equal(client(newBase, oldBase + '/').api.getServiceBase(), newBase)
})
check('LAN service override is preserved', () => {
  assert.equal(client(newBase, 'http://192.168.1.10:18000').api.getServiceBase(), 'http://192.168.1.10:18000')
})
check('Another domain override is preserved', () => {
  assert.equal(client(newBase, 'https://farm.example.org/agriscan').api.getServiceBase(), 'https://farm.example.org/agriscan')
})
check('Other old-domain path is preserved', () => {
  assert.equal(client(newBase, 'https://flowly-ai.top/other').api.getServiceBase(), 'https://flowly-ai.top/other')
})
check('Explicit proxy setting is preserved', () => {
  assert.equal(client(newBase, '').api.getServiceBase(), '')
})
check('Explicit debug build default does not migrate official override', () => {
  assert.equal(client('http://192.168.1.10:18000', oldBase).api.getServiceBase(), oldBase)
})
check('Development proxy build does not migrate official override', () => {
  assert.equal(client('', oldBase).api.getServiceBase(), oldBase)
})
check('Fresh install uses new compiled default and correct API prefix', () => {
  const c = client(newBase)
  assert.equal(c.api.getServiceBase(), newBase)
  assert.equal(c.api.endpoint('/auth/login'), newBase + '/api/auth/login')
})
check('Old token is not copied or returned for the new domain', () => {
  const key = 'agriscan-mobile-token:' + oldBase
  const c = client(newBase, oldBase, {[key]: 'old-token'})
  assert.equal(c.api.getToken(), null)
  assert.equal(c.storage.get(key), 'old-token')
  assert.equal(c.storage.has('agriscan-mobile-token:' + newBase), false)
})
check('Migration requires fresh login even if a cached new-domain token existed', () => {
  const c = client(newBase, oldBase, {['agriscan-mobile-token:' + newBase]: 'stale-new-token'})
  assert.equal(c.api.getToken(), null)
  c.api.setToken('fresh-token')
  assert.equal(c.api.getToken(), 'fresh-token')
})
check('Custom service token remains isolated and intact', () => {
  const custom = 'https://farm.example.org'
  const c = client(newBase, custom, {['agriscan-mobile-token:' + custom]: 'custom-token', ['agriscan-mobile-token:' + oldBase]: 'old-token'})
  assert.equal(c.api.getToken(), 'custom-token')
})
fs.writeFileSync('.runtime/domain-migration-20261029/service-behavior.json', JSON.stringify({source: 'Actual mobile/src/api.ts transpiled in memory; isolated localStorage', passed: results.length, failed: 0, cases: results}, null, 2))
console.log(JSON.stringify({passed: results.length, failed: 0}))
