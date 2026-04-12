/**
 * CommandsModal — generates actionable SSH commands for a discovered pivot path.
 * Shows four output formats: ProxyJump, proxychains, walkthrough, SSH config.
 */
import { useState, useEffect } from 'react'
import type { PathCommands, PathCommandsResponse, PathFinderRequest } from '../types'
import { generateCommands } from '../api/graph'
import styles from './CommandsModal.module.css'

type Tab = 'proxyjump' | 'proxychains' | 'walkthrough' | 'ssh_config'

const TAB_LABELS: Record<Tab, string> = {
  proxyjump: 'ProxyJump',
  proxychains: 'proxychains',
  walkthrough: 'Walkthrough',
  ssh_config: 'SSH Config',
}

const TAB_ORDER: Tab[] = ['proxyjump', 'proxychains', 'walkthrough', 'ssh_config']

interface Props {
  opId: string
  request: PathFinderRequest
  onClose: () => void
}

function tabContent(path: PathCommands, tab: Tab): string {
  switch (tab) {
    case 'proxyjump':    return path.proxyjump
    case 'proxychains':  return path.proxychains
    case 'walkthrough':  return path.walkthrough
    case 'ssh_config':   return path.ssh_config
  }
}

export default function CommandsModal({ opId, request, onClose }: Props) {
  const [data, setData] = useState<PathCommandsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('proxyjump')
  const [pathIdx, setPathIdx] = useState(0)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    generateCommands(opId, request)
      .then(resp => {
        setData(resp)
        setLoading(false)
      })
      .catch(() => {
        setError('Failed to generate commands.')
        setLoading(false)
      })
  }, [opId, request])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function handleCopy() {
    if (!data || !data.paths[pathIdx]) return
    const text = tabContent(data.paths[pathIdx], tab)
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  const path = data?.paths[pathIdx] ?? null

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.tabs}>
            {TAB_ORDER.map(t => (
              <button
                key={t}
                className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`}
                onClick={() => setTab(t)}
              >
                {TAB_LABELS[t]}
              </button>
            ))}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Body */}
        <div className={styles.modalBody}>
          {loading && <p className={styles.status}>Generating commands…</p>}
          {error && <p className={styles.errorMsg}>{error}</p>}

          {data && data.paths.length === 0 && (
            <p className={styles.status}>No paths found between the selected hosts.</p>
          )}

          {data && data.paths.length > 0 && (
            <>
              {/* Path selector (only if multiple paths) */}
              {data.paths.length > 1 && (
                <div className={styles.pathSelector}>
                  <span className={styles.selectorLabel}>Path:</span>
                  {data.paths.map((_, i) => (
                    <button
                      key={i}
                      className={`${styles.pathBtn} ${pathIdx === i ? styles.pathBtnActive : ''}`}
                      onClick={() => setPathIdx(i)}
                    >
                      {i + 1}
                    </button>
                  ))}
                  {data.truncated && (
                    <span className={styles.truncatedNote}>results capped at 30</span>
                  )}
                </div>
              )}

              {path && (
                <div className={styles.codeBlock}>
                  <div className={styles.codeHeader}>
                    <span className={styles.codeLabel}>{TAB_LABELS[tab]}</span>
                    <button
                      className={`${styles.copyBtn} ${copied ? styles.copyBtnDone : ''}`}
                      onClick={handleCopy}
                    >
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <pre className={styles.pre}>{tabContent(path, tab)}</pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
