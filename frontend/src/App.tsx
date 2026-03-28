/**
 * App root — manages which page is displayed based on selected operation.
 */
import { useState } from 'react'
import type { Operation } from './types'
import OpSelector from './pages/OpSelector'
import Workspace from './pages/Workspace'

export default function App() {
  const [selectedOp, setSelectedOp] = useState<Operation | null>(null)

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
