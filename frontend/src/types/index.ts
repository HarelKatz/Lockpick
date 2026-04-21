/**
 * TypeScript interfaces matching backend Pydantic schemas.
 */

export interface Operation {
  id: string
  name: string
  description: string | null
  created_at: string
}

export interface OpStats {
  host_count: number
  credential_count: number
  connection_count: number
  total_records: number
  latest_activity_at: string | null
}

export interface ImportResponse {
  op_id: string
  op_name: string
}

export interface SearchResult {
  type: 'host' | 'host_ip' | 'host_user' | 'credential' | 'connection'
  host_id: string | null
  credential_id: string | null
  connection_id: string | null
  nickname: string | null
  matched_field: string
  snippet: string
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  total: number
}

export interface ActivityLog {
  id: string
  op_id: string
  action: string
  entity_type: string
  entity_id: string | null
  detail: string | null
  created_at: string
}

export interface HostIP {
  id: string
  host_id: string
  ip_address: string
  source: 'manual' | 'parsed'
  addr_type: 'ipv4' | 'ipv6' | 'hostname'
  first_seen_at: string
}

export interface SudoRule {
  id: string
  host_id: string
  op_id: string
  subject: string
  subject_type: 'user' | 'group'
  run_as: string
  commands: string
  nopasswd: boolean
  raw_line: string | null
  created_at: string
}

export interface HostUser {
  id: string
  host_id: string
  username: string
  shell: string | null
  home_dir: string | null
  source: 'manual' | 'passwd_file' | 'authorized_keys' | 'log_evidence'
  created_at: string
}

export interface Host {
  id: string
  op_id: string
  nickname: string
  comment: string | null
  created_at: string
  ips: HostIP[]
  users: HostUser[]
}

export interface Credential {
  id: string
  op_id: string
  cred_type: 'password' | 'private_key' | 'public_key'
  name: string | null
  value: string
  fingerprint: string | null   // inferred by backend
  key_type: string | null      // inferred by backend
  passphrase: string | null
  comment: string | null
  created_at: string
}

export interface CredentialLink {
  id: string
  credential_id: string
  host_id: string
  username: string | null
  host_user_id: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source: string | null
}

export type AuthMethod = 'publickey' | 'password' | 'keyboard-interactive' | 'hostbased' | 'unknown'

export interface ConnectionRecord {
  id: string
  op_id: string
  src_host_id: string | null
  src_ip: string
  src_user: string | null
  dst_host_id: string | null
  dst_ip: string
  dst_user: string | null
  connection_type: 'ssh' | 'scp' | 'rsync' | 'sftp' | 'ssh_copy_id' | 'unknown'
  direction_context: 'from_src_logs' | 'from_dst_logs'
  auth_method: AuthMethod | null
  credential_id: string | null
  timestamp: string | null
  raw_line: string | null
  source_file: string
  created_at: string
}

// ─── Request bodies ───────────────────────────────────────────────────────────

export interface UpdateOperationRequest {
  name?: string
  description?: string | null
}

export interface UpdateHostRequest {
  nickname?: string
  comment?: string | null
}

export interface UpdateCredentialRequest {
  name?: string | null
  value?: string
  passphrase?: string | null
  comment?: string | null
}

export interface UpdateCredentialLinkRequest {
  username?: string | null
  relationship_type?: CredentialLink['relationship_type']
  file_source?: string | null
}

export interface UpdateConnectionRequest {
  src_host_id?: string | null
  src_ip?: string
  src_user?: string | null
  dst_host_id?: string | null
  dst_ip?: string
  dst_user?: string | null
  connection_type?: ConnectionRecord['connection_type']
  direction_context?: ConnectionRecord['direction_context']
  auth_method?: AuthMethod | null
  credential_id?: string | null
  timestamp?: string | null
  raw_line?: string | null
  source_file?: string
}

export interface CreateOperationRequest {
  name: string
  description?: string | null
}

export interface CreateHostRequest {
  nickname: string
  comment?: string | null
}

export interface CreateHostIPRequest {
  ip_address: string
  source?: 'manual' | 'parsed'
}

export interface CreateCredentialRequest {
  cred_type: 'password' | 'private_key' | 'public_key'
  name?: string | null
  value: string
  passphrase?: string | null   // for encrypted private keys
  comment?: string | null
}

export interface CreateCredentialLinkRequest {
  credential_id: string
  host_id: string
  username?: string | null
  host_user_id?: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source?: string | null
}

export interface CreateHostUserRequest {
  username: string
  shell?: string | null
  home_dir?: string | null
  source?: HostUser['source']
}

// ─── Graph ────────────────────────────────────────────────────────────────────

export type Confidence = 'confirmed' | 'observed' | 'indicator'

export type EvidenceType = 'key_match' | 'connection_log' | 'bash_history' | 'known_hosts'

export interface EvidenceItem {
  type: EvidenceType
  detail: string
  credential_id: string | null
  credential_fingerprint: string | null
  credential_name: string | null
  connection_type: string | null
  src_user: string | null
  dst_user: string | null
  auth_method: string | null
  timestamp: string | null
  source_file: string | null
  confidence: Confidence
}

export interface PivotableUser {
  src_user: string
  dst_user: string
  method: 'key' | 'password' | 'connection'
  credential_id: string | null
}

export interface GraphNode {
  host_id: string
  nickname: string
  ips: string[]
  user_count: number
  credential_count: number
}

export interface GraphEdge {
  src_host_id: string
  dst_host_id: string
  confidence: Confidence
  evidence: EvidenceItem[]
  pivotable_users: PivotableUser[]
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface CreateConnectionRequest {
  src_host_id?: string | null
  src_ip: string
  src_user?: string | null
  dst_host_id?: string | null
  dst_ip: string
  dst_user?: string | null
  connection_type: 'ssh' | 'scp' | 'rsync' | 'sftp' | 'ssh_copy_id' | 'unknown'
  direction_context: 'from_src_logs' | 'from_dst_logs'
  auth_method?: AuthMethod | null
  credential_id?: string | null
  timestamp?: string | null
  raw_line?: string | null
  source_file: string
}

// ─── Evidence Files ───────────────────────────────────────────────────────────

export interface UploadFile {
  safe_name: string       // UUID-prefixed filename (used in download URL)
  original_name: string   // filename without UUID prefix (for display)
  size_bytes: number
  host_ids: string[]      // host IDs that reference this file
  uploaded_at: string     // ISO 8601 UTC, from file mtime
}

// ─── Upload ───────────────────────────────────────────────────────────────────

export type UploadFileType =
  | 'authorized_keys'
  | 'known_hosts'
  | 'ssh_config'
  | 'private_key'
  | 'public_key'
  | 'auth_log'
  | 'wtmp'
  | 'bash_history'
  | 'passwd'
  | 'shadow'
  | 'sshd_config'
  | 'nmap_xml'
  | 'etc_hosts'
  | 'sudoers'

export interface UploadSummary {
  new_credentials: number
  new_credential_links: number
  new_connections: number
  new_hosts: number
  warnings: string[]
}

export interface UploadResult {
  ok: boolean
  filename: string
  file_type: string
  stats: Record<string, unknown>
  summary: UploadSummary
  pivot_opportunities: string[]
}

// ── Path Finding ──────────────────────────────────────────────────────────────

export type WaypointPosition = 'anywhere' | 'after' | 'before'

export interface WaypointConstraint {
  host_id: string
  position: WaypointPosition
  relative_to: string | null
}

export interface PathFinderRequest {
  src_host_id: string
  dst_host_id: string
  mode: 'shortest' | 'all'
  waypoints: WaypointConstraint[]
}

export interface PathResult {
  host_ids: string[]
  edges: GraphEdge[]
}

export interface PathFinderResponse {
  paths: PathResult[]
  truncated: boolean
}

export interface PathCommands {
  host_ids: string[]
  proxyjump: string
  proxychains: string
  walkthrough: string
  ssh_config: string
}

export interface PathCommandsResponse {
  paths: PathCommands[]
  truncated: boolean
}
