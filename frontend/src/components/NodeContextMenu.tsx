/**
 * Right-click context menu for graph nodes.
 * Positioned at fixed screen coordinates from cytoscape cxttap event.
 */
import { useEffect, useRef } from 'react'
import type { GraphNode } from '../types'
import styles from './NodeContextMenu.module.css'

interface Props {
  node: GraphNode
  x: number
  y: number
  isLocked: boolean
  onExpand: (node: GraphNode, evidenceType: 'all' | 'key_match' | 'connection_log' | 'indicator') => void
  onHide: (node: GraphNode) => void
  onToggleLock: () => void
  onClose: () => void
}

export default function NodeContextMenu({ node, x, y, isLocked, onExpand, onHide, onToggleLock, onClose }: Props) {
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

  function item(label: string, action: () => void) {
    return (
      <button
        key={label}
        className={styles.item}
        onClick={() => { action(); onClose() }}
      >
        {label}
      </button>
    )
  }

  return (
    <div
      ref={menuRef}
      className={styles.menu}
      style={{ top: y, left: x }}
    >
      <div className={styles.header}>{node.nickname}</div>
      <div className={styles.separator} />
      {item('Expand all neighbors', () => onExpand(node, 'all'))}
      {item('Expand by key matches', () => onExpand(node, 'key_match'))}
      {item('Expand by connection logs', () => onExpand(node, 'connection_log'))}
      {item('Expand by indicators', () => onExpand(node, 'indicator'))}
      <div className={styles.separator} />
      {item(isLocked ? 'Unlock node' : 'Lock node', () => onToggleLock())}
      <div className={styles.separator} />
      {item('Hide this node', () => onHide(node))}
    </div>
  )
}
