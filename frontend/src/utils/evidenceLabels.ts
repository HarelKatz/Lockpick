/**
 * User-facing labels for graph edge evidence types — the single source of truth,
 * shared by EdgeDetailPanel and PathDetailPanel (incl. its Markdown export).
 *
 * The `Record<EvidenceType, string>` annotation is the guard: when the backend
 * gains an evidence type and `EvidenceType` is widened, a missing label here is a
 * compile error rather than a raw snake_case slug leaking into the UI.
 *
 * Wording follows house style — acronyms uppercase, real command names verbatim
 * lowercase (cf. CONN_TYPE_LABELS in pages/Workspace.tsx).
 */
import type { EvidenceType } from '../types'

export const EVIDENCE_LABELS: Record<EvidenceType, string> = {
  key_match: 'Key Match',
  connection_log: 'Connection Log',
  bash_history: 'Bash History',
  known_hosts: 'Known Hosts',
  arp: 'ARP Cache',
  ip_neigh: 'IP Neighbor',
  iptables: 'iptables',
  nftables: 'nftables',
  authorized_keys: 'Authorized Key ACL',
}
