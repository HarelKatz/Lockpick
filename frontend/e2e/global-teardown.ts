import { rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const HERE = path.dirname(fileURLToPath(import.meta.url))

/** Best-effort cleanup of the throwaway e2e DB/uploads and the op-id marker. */
export default async function globalTeardown() {
  for (const p of [path.join(HERE, '.data'), path.join(HERE, '.op-id'), path.join(HERE, '.op-id-scale')]) {
    try {
      rmSync(p, { recursive: true, force: true })
    } catch {
      /* ignore */
    }
  }
}
