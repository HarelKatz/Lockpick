/**
 * EditModal — thin modal shell wrapping entity-specific edit forms.
 * Closes on Esc or backdrop click.
 */
import { useEffect } from 'react'
import styles from './EditModal.module.css'

interface Props {
  title: string
  onClose: () => void
  children: React.ReactNode
}

export default function EditModal({ title, onClose, children }: Props) {
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
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className={styles.body}>
          {children}
        </div>
      </div>
    </div>
  )
}
