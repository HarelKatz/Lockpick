import { CONFIDENCE_CONFIRMED, CONFIDENCE_OBSERVED, CONFIDENCE_MUTED } from '../theme'
import type { Confidence, EvidenceItem, GraphEdge } from '../types'
import { computeEdgeLabel, confidenceColor } from './edgeDisplay'

function ev(partial: Partial<EvidenceItem>): EvidenceItem {
  return {
    type: 'connection_log',
    detail: '',
    credential_id: null,
    credential_fingerprint: null,
    credential_name: null,
    connection_type: null,
    src_user: null,
    dst_user: null,
    auth_method: null,
    timestamp: null,
    source_file: null,
    confidence: 'observed',
    ...partial,
  }
}

function edge(evidence: EvidenceItem[], confidence: Confidence = 'observed'): GraphEdge {
  return { src_host_id: 'a', dst_host_id: 'b', confidence, evidence, pivotable_users: [] }
}

describe('computeEdgeLabel', () => {
  it('uses the uppercased connection_type of a connection_log', () => {
    expect(computeEdgeLabel(edge([ev({ type: 'connection_log', connection_type: 'ssh' })]))).toBe('SSH')
    expect(computeEdgeLabel(edge([ev({ type: 'connection_log', connection_type: 'scp' })]))).toBe('SCP')
  })

  it('prefers a typed connection_log over key_match, regardless of order', () => {
    const km = ev({ type: 'key_match' })
    const conn = ev({ type: 'connection_log', connection_type: 'sftp' })
    expect(computeEdgeLabel(edge([km, conn]))).toBe('SFTP')
    expect(computeEdgeLabel(edge([conn, km]))).toBe('SFTP')
  })

  it('falls through a connection_log with no connection_type', () => {
    expect(computeEdgeLabel(edge([ev({ type: 'connection_log', connection_type: null }), ev({ type: 'key_match' })]))).toBe('key match')
  })

  it('labels key_match, then bash_history, then known_hosts', () => {
    expect(computeEdgeLabel(edge([ev({ type: 'key_match' })]))).toBe('key match')
    expect(computeEdgeLabel(edge([ev({ type: 'bash_history' })]))).toBe('bash history')
    expect(computeEdgeLabel(edge([ev({ type: 'known_hosts' })]))).toBe('known hosts')
  })

  it('prefers key_match over bash_history/known_hosts', () => {
    expect(computeEdgeLabel(edge([ev({ type: 'bash_history' }), ev({ type: 'key_match' })]))).toBe('key match')
  })

  it('prefers bash_history over known_hosts', () => {
    expect(computeEdgeLabel(edge([ev({ type: 'known_hosts' }), ev({ type: 'bash_history' })]))).toBe('bash history')
  })

  it('defaults to "connection" when no evidence matches', () => {
    expect(computeEdgeLabel(edge([]))).toBe('connection')
  })
})

describe('confidenceColor', () => {
  it('maps confirmed/observed to their theme colors', () => {
    expect(confidenceColor('confirmed')).toBe(CONFIDENCE_CONFIRMED)
    expect(confidenceColor('observed')).toBe(CONFIDENCE_OBSERVED)
  })

  it('maps indicator and any unknown value to the muted color', () => {
    expect(confidenceColor('indicator')).toBe(CONFIDENCE_MUTED)
    expect(confidenceColor('whatever')).toBe(CONFIDENCE_MUTED)
  })
})
