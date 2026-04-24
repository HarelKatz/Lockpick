/**
 * Collection tab body — "Download script" button + "Import archive" drop zone.
 * Lives inside HostDetailSidebar; always scoped to a specific host.
 */
import { useRef, useState } from 'react'
import { downloadCollectionScript, importArchive } from '../api/collection'
import { ApiError } from '../api/client'
import type { ArchiveImportResult } from '../types'
import styles from './HostDetailSidebar.module.css'

interface Props {
  opId: string
  hostId: string
  onImported?: () => void
}

export default function CollectionPanel({ opId, hostId, onImported }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ArchiveImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  async function handleFile(file: File) {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await importArchive(opId, hostId, file)
      setResult(res)
      onImported?.()
    } catch (e) {
      if (e instanceof ApiError) {
        const detail =
          typeof e.body === 'object' && e.body !== null && 'detail' in e.body
            ? String((e.body as { detail: unknown }).detail)
            : `HTTP ${e.status}`
        setError(detail)
      } else {
        setError('Import failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault()
    setDragActive(true)
  }

  function onDragLeave() {
    setDragActive(false)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  return (
    <div className={styles.section}>
      <div className={styles.collectionSection}>
        <div className={styles.sectionLabel}>Collection script</div>
        <p className={styles.collectionHelp}>
          Download and run on the target host. Produces a tarball to import below.
        </p>
        <button
          className={styles.downloadBtn}
          onClick={() => downloadCollectionScript(opId)}
        >
          Download script
        </button>
      </div>

      <div className={styles.collectionSection}>
        <div className={styles.sectionLabel}>Import archive</div>
        <div
          className={`${styles.archiveDropZone} ${dragActive ? styles.archiveDropZoneActive : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".tar.gz,.tgz,application/gzip,application/x-gzip"
            style={{ display: 'none' }}
            onChange={onInputChange}
          />
          {busy
            ? 'Importing…'
            : 'Drop .tar.gz here or click to browse'}
        </div>
        {error && <p className={styles.noteError}>{error}</p>}
        {result && <ImportResultView result={result} />}
      </div>
    </div>
  )
}

function ImportResultView({ result }: { result: ArchiveImportResult }) {
  return (
    <div className={styles.archiveResult}>
      <div className={styles.archiveSummary}>
        <span>{result.files_processed} processed</span>
        {result.files_skipped > 0 && (
          <span className={styles.archiveSkipped}>{result.files_skipped} skipped</span>
        )}
        <span>·</span>
        <span>{result.totals.new_credentials} creds</span>
        <span>{result.totals.new_credential_links} links</span>
        <span>{result.totals.new_connections} connections</span>
        <span>{result.totals.new_hosts} hosts</span>
        <span>{result.totals.new_sudo_rules} sudo rules</span>
      </div>
      {result.pivot_opportunities.length > 0 && (
        <div className={styles.archivePivots}>
          <div className={styles.sectionLabel}>New pivots</div>
          {result.pivot_opportunities.map((p, i) => (
            <div key={i} className={styles.archivePivot}>{p}</div>
          ))}
        </div>
      )}
      <details className={styles.archiveDetails}>
        <summary>Per-file ({result.per_file.length})</summary>
        {result.per_file.map((f, i) => (
          <div key={i} className={styles.archiveFile}>
            <div className={styles.archiveFileHeader}>
              <span className={f.ok ? styles.archiveOk : styles.archiveSkip}>
                {f.ok ? '✓' : '−'}
              </span>
              <span className={styles.archiveFilename}>{f.filename}</span>
            </div>
            {f.summary.warnings.length > 0 && (
              <div className={styles.archiveWarnings}>
                {f.summary.warnings.map((w, j) => (
                  <div key={j} className={styles.archiveWarning}>{w}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </details>
    </div>
  )
}
