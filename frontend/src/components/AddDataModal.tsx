/**
 * AddDataModal — floating action button (FAB) + modal with Manual Entry / File Upload tabs.
 */
import { useState, useEffect } from 'react'
import type { Host, Credential } from '../types'
import ManualEntryForm from './ManualEntryForm'
import FileUploadForm from './FileUploadForm'
import styles from './AddDataModal.module.css'

type Tab = 'manual' | 'upload'

interface Props {
  opId: string
  hosts: Host[]
  credentials: Credential[]
  onDataAdded: () => void
}

function Modal({
  opId,
  hosts,
  credentials,
  onClose,
  onDataAdded,
}: {
  opId: string
  hosts: Host[]
  credentials: Credential[]
  onClose: () => void
  onDataAdded: () => void
}) {
  const [tab, setTab] = useState<Tab>('manual')

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function handleDataAdded() {
    onDataAdded()
    // Keep modal open so user can add more entries
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        {/* Modal header */}
        <div className={styles.modalHeader}>
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${tab === 'manual' ? styles.tabActive : ''}`}
              onClick={() => setTab('manual')}
            >
              Manual Entry
            </button>
            <button
              className={`${styles.tab} ${tab === 'upload' ? styles.tabActive : ''}`}
              onClick={() => setTab('upload')}
            >
              File Upload
            </button>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {/* Modal body */}
        <div className={styles.modalBody}>
          {tab === 'manual' && (
            <ManualEntryForm opId={opId} hosts={hosts} credentials={credentials} onSuccess={handleDataAdded} />
          )}
          {tab === 'upload' && (
            <FileUploadForm opId={opId} hosts={hosts} onSuccess={handleDataAdded} />
          )}
        </div>
      </div>
    </div>
  )
}

export default function AddDataModal({ opId, hosts, credentials, onDataAdded }: Props) {
  const [open, setOpen] = useState(false)

  function handleClose() {
    setOpen(false)
  }

  function handleDataAdded() {
    onDataAdded()
  }

  return (
    <>
      {/* FAB */}
      <button
        className={styles.fab}
        onClick={() => setOpen(true)}
        aria-label="Add data"
        title="Add data"
      >
        +
      </button>

      {/* Modal */}
      {open && (
        <Modal
          opId={opId}
          hosts={hosts}
          credentials={credentials}
          onClose={handleClose}
          onDataAdded={handleDataAdded}
        />
      )}
    </>
  )
}
