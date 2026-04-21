/**
 * Right sidebar — shows detail for a selected graph node.
 * If a full Host object is provided, shows tabs: Info | Sudo Rules.
 */
import { useState, useEffect, useCallback } from 'react'
import type { GraphEdge, GraphNode, Host, SudoRule } from '../types'
import { getSudoRules, deleteSudoRule } from '../api/hosts'
import styles from './HostDetailSidebar.module.css'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  indicator: 'Indicator',
}

const ADDR_TYPE_LABEL: Record<string, string> = {
  ipv4: 'IPv4',
  ipv6: 'IPv6',
  hostname: 'hostname',
}

type Tab = 'info' | 'sudo'

interface Props {
  node: GraphNode
  edges: GraphEdge[]
  host?: Host | null
  onClose: () => void
}

export default function HostDetailSidebar({ node, edges, host, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('info')
  const [sudoRules, setSudoRules] = useState<SudoRule[]>([])
  const [sudoLoading, setSudoLoading] = useState(false)
  const [sudoError, setSudoError] = useState<string | null>(null)

  const loadSudoRules = useCallback(async () => {
    if (!host) return
    setSudoLoading(true)
    setSudoError(null)
    try {
      const rules = await getSudoRules(host.id)
      setSudoRules(rules)
    } catch {
      setSudoError('Failed to load sudo rules.')
    } finally {
      setSudoLoading(false)
    }
  }, [host])

  useEffect(() => {
    if (tab === 'sudo') {
      loadSudoRules()
    }
  }, [tab, loadSudoRules])

  // Reset tab when a different node is selected
  useEffect(() => {
    setTab('info')
    setSudoRules([])
  }, [node.host_id])

  async function handleDeleteRule(ruleId: string) {
    if (!host) return
    try {
      await deleteSudoRule(host.id, ruleId)
      setSudoRules(prev => prev.filter(r => r.id !== ruleId))
    } catch {
      setSudoError('Failed to delete rule.')
    }
  }

  const outgoing = edges.filter(e => e.src_host_id === node.host_id)
  const incoming = edges.filter(e => e.dst_host_id === node.host_id)

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.title}>{node.nickname}</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
      </div>

      {host && (
        <div className={styles.tabBar}>
          <button
            className={`${styles.tabBtn} ${tab === 'info' ? styles.tabActive : ''}`}
            onClick={() => setTab('info')}
          >
            Info
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'sudo' ? styles.tabActive : ''}`}
            onClick={() => setTab('sudo')}
          >
            Sudo Rules
          </button>
        </div>
      )}

      <div className={styles.body}>
        {(!host || tab === 'info') && (
          <>
            {host && host.ips.length > 0 ? (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>IPs / Hostnames</div>
                <div className={styles.addrList}>
                  {host.ips.map(ip => (
                    <div key={ip.id} className={styles.addrRow}>
                      <span className={styles.chip}>{ip.ip_address}</span>
                      <span className={styles.addrTypeBadge}>
                        {ADDR_TYPE_LABEL[ip.addr_type] ?? ip.addr_type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : node.ips.length > 0 ? (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>IPs</div>
                <div className={styles.chips}>
                  {node.ips.map(ip => (
                    <span key={ip} className={styles.chip}>{ip}</span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className={styles.section}>
              <div className={styles.stats}>
                <span className={styles.statItem}>
                  <span className={styles.statValue}>{node.user_count}</span>
                  <span className={styles.statLabel}>users</span>
                </span>
                <span className={styles.statItem}>
                  <span className={styles.statValue}>{node.credential_count}</span>
                  <span className={styles.statLabel}>credentials</span>
                </span>
              </div>
            </div>

            {outgoing.length > 0 && (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>Outgoing ({outgoing.length})</div>
                {outgoing.map(e => (
                  <EdgeSummary key={`${e.src_host_id}__${e.dst_host_id}`} edge={e} perspective="dst" />
                ))}
              </div>
            )}

            {incoming.length > 0 && (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>Incoming ({incoming.length})</div>
                {incoming.map(e => (
                  <EdgeSummary key={`${e.src_host_id}__${e.dst_host_id}`} edge={e} perspective="src" />
                ))}
              </div>
            )}

            {outgoing.length === 0 && incoming.length === 0 && (
              <p className={styles.empty}>No connections found.</p>
            )}
          </>
        )}

        {host && tab === 'sudo' && (
          <div className={styles.section}>
            {sudoLoading && <p className={styles.empty}>Loading…</p>}
            {sudoError && <p className={styles.sudoError}>{sudoError}</p>}
            {!sudoLoading && !sudoError && sudoRules.length === 0 && (
              <p className={styles.empty}>No sudo rules found.</p>
            )}
            {!sudoLoading && sudoRules.map(rule => (
              <div key={rule.id} className={styles.sudoRule}>
                <div className={styles.sudoRuleHeader}>
                  <span className={styles.sudoSubject}>
                    {rule.subject}
                    {rule.subject_type === 'group' && (
                      <span className={styles.groupBadge}>group</span>
                    )}
                  </span>
                  <span className={styles.sudoRunAs}>→ {rule.run_as}</span>
                  {rule.nopasswd && (
                    <span className={styles.nopasswdBadge}>NOPASSWD</span>
                  )}
                  <button
                    className={styles.deleteRuleBtn}
                    onClick={() => handleDeleteRule(rule.id)}
                    aria-label={`Delete sudo rule for ${rule.subject}`}
                    title="Delete rule"
                  >
                    ✕
                  </button>
                </div>
                <div className={styles.sudoCommands}>{rule.commands}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EdgeSummary({ edge, perspective }: { edge: GraphEdge; perspective: 'src' | 'dst' }) {
  const otherId = perspective === 'dst' ? edge.dst_host_id : edge.src_host_id
  const confidenceClass = `conf_${edge.confidence}` as keyof typeof styles

  return (
    <div className={styles.edgeSummary}>
      <span className={`${styles.confBadge} ${styles[confidenceClass]}`}>
        {CONFIDENCE_LABEL[edge.confidence]}
      </span>
      <span className={styles.edgeTarget}>{otherId.slice(0, 8)}…</span>
      <span className={styles.edgeCount}>{edge.evidence.length} evidence</span>
    </div>
  )
}
