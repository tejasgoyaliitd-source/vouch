// Hosted, each browser works on its own copy of the demo data, picked by this cookie. The local app ignores it.
if (!/(?:^|; )vouch_ws=/.test(document.cookie)) {
  const id = Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, '0')).join('')
  document.cookie = `vouch_ws=${id}; path=/; max-age=31536000; SameSite=Lax`
}

const check = (p) => (r) => { if (!r.ok) throw new Error(`${r.status} ${p}`); return r.json() }
export const get = (p) => fetch(`/api${p}`).then(check(p))
export const post = (p, body) => fetch(`/api${p}`, { method: 'POST', body }).then(check(p))
let statusReq
export const tooBig = async (file) => {
  const mb = await (statusReq ||= get('/status')).then((s) => s.max_upload_mb || 15, () => 15)
  return file.size > mb * 1024 * 1024 ? `${file.name} is ${(file.size / 1048576).toFixed(1)} MB. Files up to ${mb} MB can be uploaded here.` : ''
}
export const postJson =(p, data) => fetch(`/api${p}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(check(p))
