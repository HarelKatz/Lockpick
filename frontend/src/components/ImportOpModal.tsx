import { useEffect, useRef, useState } from 'react'
import { importOp } from '../api/export_import'
import styles from './ImportOpModal.module.css'

interface Props {
  onClose: () => void
  onImported: (opId: string) => void
}

export default function ImportOpModal({ onClose, onImported }: Props) {
  const [nameOverride, setNameOverride] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Esc to close
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  function setJsonFile(f: File) {
    if (!f.name.endsWith('.json')) {
      setError('Only .json export files are supported.')
      return
    }
    setFile(f)
    setError(null)
  }

  function handleDragOver(e: React.DragEvent) { e.preventDefault(); setDragging(true) }
  function handleDragLeave() { setDragging(false) }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) setJsonFile(f)
  }
  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) setJsonFile(f)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) { setError('Select a .json export file.'); return }

    setLoading(true)
    setError(null)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      if (data.lockpick_export_version !== 1) {
        setError('Unrecognized export format (expected lockpick_export_version: 1).')
        setLoading(false)
        return
      }
      const result = await importOp(data, nameOverride.trim() || undefined)
      onImported(result.op_id)
    } catch (err: unknown) {
      if (err instanceof SyntaxError) {
        setError('Invalid JSON file.')
      } else if (err && typeof err === 'object' && 'body' in err) {
        const body = (err as { body: unknown }).body
        if (body && typeof body === 'object' && 'detail' in body) {
          setError(String((body as { detail: unknown }).detail))
        } else {
          setError('Import failed.')
        }
      } else {
        setError('Import failed.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>Import Operation</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        <form className={styles.body} onSubmit={handleSubmit}>
          <p className={styles.note}>
            Imports a Lockpick export file as a new operation. Uploaded evidence files are not
            included in exports and must be re-uploaded if needed.
          </p>

          {/* Drop zone */}
          <div
            className={`${styles.dropZone} ${dragging ? styles.dragging : ''} ${file ? styles.hasFile : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
            aria-label="Drop export JSON here or click to browse"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className={styles.hiddenInput}
              onChange={handleFileInput}
              tabIndex={-1}
            />
            {file ? (
              <div className={styles.fileInfo}>
                <span>📄 {file.name}</span>
                <span className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            ) : (
              <div className={styles.dropPrompt}>
                <span className={styles.dropIcon}>⬆</span>
                <span>Drop .json export here or click to browse</span>
              </div>
            )}
          </div>

          {/* Optional name override */}
          <div className={styles.field}>
            <label className={styles.label}>Operation name (optional)</label>
            <input
              className={styles.input}
              type="text"
              placeholder="Leave blank to use original name + '(imported)'"
              value={nameOverride}
              onChange={e => setNameOverride(e.target.value)}
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onClose}>Cancel</button>
            <button
              type="submit"
              className={styles.importBtn}
              disabled={loading || !file}
            >
              {loading ? 'Importing…' : 'Import'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
