/**
 * App root — manages which page is displayed based on selected operation.
 * The selected op is persisted to sessionStorage so a page refresh
 * returns the user to the same workspace.
 */
import { useState, useEffect } from 'react'
import type { Operation } from './types'
import OpSelector from './pages/OpSelector'
import Workspace from './pages/Workspace'

const SESSION_KEY = 'lockpick_selected_op'

export default function App() {
  const [selectedOp, setSelectedOp] = useState<Operation | null>(() => {
    try {
      const stored = sessionStorage.getItem(SESSION_KEY)
      return stored ? (JSON.parse(stored) as Operation) : null
    } catch {
      return null
    }
  })

  useEffect(() => {
    if (selectedOp) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(selectedOp))
    } else {
      sessionStorage.removeItem(SESSION_KEY)
    }
  }, [selectedOp])

  if (selectedOp) {
    return (
      <Workspace
        op={selectedOp}
        onBack={() => setSelectedOp(null)}
      />
    )
  }

  return <OpSelector onSelectOp={setSelectedOp} />
}
