/**
 * ConfirmDeleteModal — reusable "Are you sure?" dialog.
 */
import { useEffect } from 'react'
import styles from './ConfirmDeleteModal.module.css'

interface Props {
  title: string
  message: string
  onConfirm: () => void
  onClose: () => void
  loading?: boolean
}

export default function ConfirmDeleteModal({ title, message, onConfirm, onClose, loading }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close" disabled={loading}>✕</button>
        </div>
        <div className={styles.body}>
          <p className={styles.message}>{message}</p>
          <div className={styles.actions}>
            <button className={styles.btnSecondary} onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button className={styles.btnDanger} onClick={onConfirm} disabled={loading}>
              {loading ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
