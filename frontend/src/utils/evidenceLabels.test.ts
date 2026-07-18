import type { EvidenceType } from '../types'
import { EVIDENCE_LABELS } from './evidenceLabels'

// Runtime mirror of the EvidenceType union (TS types vanish at compile time).
// Typed as EvidenceType[], so a value the union doesn't carry fails to compile.
const ALL_EVIDENCE_TYPES: EvidenceType[] = [
  'key_match',
  'connection_log',
  'bash_history',
  'known_hosts',
  'arp',
  'ip_neigh',
  'iptables',
  'nftables',
]

describe('EVIDENCE_LABELS', () => {
  it('resolves a label for every evidence type the backend can send', () => {
    // The panels render `EVIDENCE_LABELS[ev.type] ?? ev.type`; a gap here is what
    // leaked raw snake_case slugs (e.g. "ip_neigh") into the UI and the Markdown
    // path export.
    for (const type of ALL_EVIDENCE_TYPES) {
      expect(EVIDENCE_LABELS[type]).toBeTruthy()
    }
  })

  it('covers exactly the union — no missing keys, no strays', () => {
    expect(Object.keys(EVIDENCE_LABELS).sort()).toEqual([...ALL_EVIDENCE_TYPES].sort())
  })

  it('labels the indicator types that previously fell through to the raw slug', () => {
    expect(EVIDENCE_LABELS.arp).toBe('ARP Cache')
    expect(EVIDENCE_LABELS.ip_neigh).toBe('IP Neighbor')
    expect(EVIDENCE_LABELS.iptables).toBe('iptables')
    expect(EVIDENCE_LABELS.nftables).toBe('nftables')
  })
})
