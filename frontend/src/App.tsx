/**
 * App root — manages which page is displayed based on selected operation.
 */
import { useState } from 'react'
import type { Operation } from './types'
import OpSelector from './pages/OpSelector'
import styles from './App.module.css'

function WorkspacePlaceholder({ op, onBack }: { op: Operation; onBack: () => void }) {
  return (
    <div className={styles.workspace}>
      <header className={styles.workspaceHeader}>
        <button className={styles.backBtn} onClick={onBack}>
          ← Operations
        </button>
        <span className={styles.opName}>{op.name}</span>
        <span className={styles.badge}>Phase 2 coming soon</span>
      </header>
      <main className={styles.workspaceMain}>
        <div className={styles.placeholder}>
          <h2>Operation: {op.name}</h2>
          {op.description && <p>{op.description}</p>}
          <p className={styles.placeholderNote}>
            The main workspace (graph view, manual entry, file upload) will be implemented in Phase 2.
          </p>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  const [selectedOp, setSelectedOp] = useState<Operation | null>(null)

  if (selectedOp) {
    return (
      <WorkspacePlaceholder
        op={selectedOp}
        onBack={() => setSelectedOp(null)}
      />
    )
  }

  return <OpSelector onSelectOp={setSelectedOp} />
}
