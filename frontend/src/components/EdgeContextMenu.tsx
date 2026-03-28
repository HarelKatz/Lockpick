/**
 * Right-click context menu for graph edges.
 */
import { useEffect, useRef } from 'react'
import type { GraphEdge, GraphNode } from '../types'
import styles from './EdgeContextMenu.module.css'

interface Props {
  edge: GraphEdge
  nodes: GraphNode[]
  x: number
  y: number
  onViewEvidence: (edge: GraphEdge) => void
  onClose: () => void
}

export default function EdgeContextMenu({ edge, nodes, x, y, onViewEvidence, onClose }: Props) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  const srcNickname = nodes.find(n => n.host_id === edge.src_host_id)?.nickname ?? edge.src_host_id
  const dstNickname = nodes.find(n => n.host_id === edge.dst_host_id)?.nickname ?? edge.dst_host_id

  return (
    <div
      ref={menuRef}
      className={styles.menu}
      style={{ top: y, left: x }}
    >
      <div className={styles.header}>
        {srcNickname} → {dstNickname}
      </div>
      <div className={styles.separator} />
      <button
        className={styles.item}
        onClick={() => { onViewEvidence(edge); onClose() }}
      >
        View evidence ({edge.evidence.length})
      </button>
    </div>
  )
}
