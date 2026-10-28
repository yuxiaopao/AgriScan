export interface PlotDraft {
  name: string
  crop: string
  area: string
  location: string
  manager: string
  latitude: string
  longitude: string
  file: File | null
  removeCover?: boolean
  savedId?: string
}

let database: Promise<IDBDatabase> | undefined

function openDrafts() {
  if (!database) database = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('agriscan-plot-drafts', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('drafts')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => {database = undefined; reject(request.error)}
  })
  return database
}

export async function readPlotDraft(key: string): Promise<PlotDraft | undefined> {
  const db = await openDrafts()
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('drafts', 'readonly')
    const request = transaction.objectStore('drafts').get(key)
    transaction.oncomplete = () => resolve(request.result)
    transaction.onabort = () => reject(transaction.error)
  })
}

export async function writePlotDraft(key: string, draft: PlotDraft | null) {
  const db = await openDrafts()
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction('drafts', 'readwrite')
    const store = transaction.objectStore('drafts')
    if (draft) store.put(draft, key)
    else store.delete(key)
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
  })
}
