import { useEffect, useRef, useState } from 'react'
import { searchOp } from '../api/search'
import type { SearchResult } from '../types'
import styles from './SearchModal.module.css'

interface Props {
  opId: string
  onClose: () => void
}

const TYPE_LABELS: Record<SearchResult['type'], string> = {
  host: 'Host',
  host_ip: 'IP Address',
  host_user: 'User Account',
  credential: 'Credential',
  connection: 'Connection',
}

const FIELD_LABELS: Record<string, string> = {
  nickname: 'name',
  comment: 'comment',
  ip_address: 'IP',
  username: 'username',
  name: 'name',
  fingerprint: 'fingerprint',
  src_ip: 'src IP',
  dst_ip: 'dst IP',
  src_user: 'src user',
  dst_user: 'dst user',
  raw_line: 'raw line',
}

export default function SearchModal({ opId, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  // Esc to close
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Debounced search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (query.length < 2) {
      setResults(null)
      setError(null)
      return
    }
    timerRef.current = setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const resp = await searchOp(opId, query)
        setResults(resp.results)
      } catch {
        setError('Search failed.')
        setResults(null)
      } finally {
        setLoading(false)
      }
    }, 300)
  }, [query, opId])

  // Group results by type
  const grouped = results
    ? (Object.keys(TYPE_LABELS) as SearchResult['type'][]).reduce<Record<string, SearchResult[]>>((acc, t) => {
        const items = results.filter(r => r.type === t)
        if (items.length) acc[t] = items
        return acc
      }, {})
    : {}

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.inputRow}>
          <span className={styles.searchIcon}>⌕</span>
          <input
            ref={inputRef}
            className={styles.input}
            type="text"
            placeholder="Search hosts, IPs, users, credentials, connections…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {loading && <span className={styles.spinner}>…</span>}
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close search">✕</button>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        {query.length >= 2 && !loading && results !== null && results.length === 0 && (
          <p className={styles.empty}>No results for "{query}"</p>
        )}

        {Object.entries(grouped).map(([type, items]) => (
          <div key={type} className={styles.group}>
            <div className={styles.groupHeader}>{TYPE_LABELS[type as SearchResult['type']]}</div>
            {items.map((r, i) => (
              <div key={i} className={styles.result}>
                <div className={styles.resultMain}>
                  {r.nickname && <span className={styles.resultNickname}>{r.nickname}</span>}
                  <span className={styles.resultSnippet}>{r.snippet}</span>
                </div>
                <span className={styles.resultField}>{FIELD_LABELS[r.matched_field] ?? r.matched_field}</span>
              </div>
            ))}
          </div>
        ))}

        {query.length < 2 && (
          <p className={styles.hint}>Type at least 2 characters to search</p>
        )}
      </div>
    </div>
  )
}
