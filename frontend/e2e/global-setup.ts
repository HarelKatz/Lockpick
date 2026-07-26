import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '..', '..')
const SEED = path.join(REPO, 'tests', 'e2e', 'seed_e2e.py')
const OP_ID_FILE = path.join(HERE, '.op-id')
const SCALE_OP_ID_FILE = path.join(HERE, '.op-id-scale')
const KEYOPTS_OP_ID_FILE = path.join(HERE, '.op-id-keyopts')

const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8137'
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`

/**
 * Seeds the isolated e2e backend with the deterministic graph fixture and writes
 * the created op id to `.op-id` for the specs to read. Waits for backend
 * readiness itself, so it is robust to webServer/globalSetup ordering.
 */
export default async function globalSetup() {
  const deadline = Date.now() + 120_000
  for (;;) {
    try {
      const r = await fetch(`${BACKEND_URL}/api/ops`)
      if (r.ok) break
    } catch {
      /* not up yet */
    }
    if (Date.now() > deadline) throw new Error(`[global-setup] backend never became ready at ${BACKEND_URL}`)
    await new Promise((res) => setTimeout(res, 1000))
  }

  const out = execFileSync(
    'uv',
    ['run', '--project', path.join(REPO, 'backend'), 'python', SEED, '--url', BACKEND_URL],
    { encoding: 'utf8' },
  )
  // The seed prints three ids as its final three stdout lines: normal, scale,
  // then key-options.
  const lines = out.trim().split('\n').map((l) => l.trim()).filter(Boolean)
  const keyOptsOpId = lines.pop()
  const scaleOpId = lines.pop()
  const opId = lines.pop()
  if (!opId || !scaleOpId || !keyOptsOpId) {
    throw new Error('[global-setup] seed did not produce all three op ids')
  }
  writeFileSync(OP_ID_FILE, opId)
  writeFileSync(SCALE_OP_ID_FILE, scaleOpId)
  writeFileSync(KEYOPTS_OP_ID_FILE, keyOptsOpId)
  console.log(`[global-setup] seeded ops normal=${opId} scale=${scaleOpId} keyopts=${keyOptsOpId}`)
}
