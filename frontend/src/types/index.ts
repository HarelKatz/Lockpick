/**
 * TypeScript interfaces matching backend Pydantic schemas.
 */

export interface Operation {
  id: string
  name: string
  description: string | null
  created_at: string
}

export interface HostIP {
  id: string
  host_id: string
  ip_address: string
  cidr: string | null
  interface_name: string | null
  source: 'manual' | 'parsed'
  first_seen_at: string
}

export interface HostUser {
  id: string
  host_id: string
  username: string
  shell: string | null
  home_dir: string | null
  source: 'manual' | 'passwd_file' | 'authorized_keys' | 'home_dir_found' | 'log_evidence'
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
  value: string
  fingerprint: string | null
  key_type: string | null
  comment: string | null
  created_at: string
}

export interface CredentialLink {
  id: string
  credential_id: string
  host_id: string
  host_user_id: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source: string | null
}

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
  timestamp: string | null
  raw_line: string | null
  source_file: string
  created_at: string
}

// ─── Request bodies ───────────────────────────────────────────────────────────

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
  cidr?: string | null
  interface_name?: string | null
  source?: 'manual' | 'parsed'
}

export interface CreateHostUserRequest {
  username: string
  shell?: string | null
  home_dir?: string | null
  source: 'manual' | 'passwd_file' | 'authorized_keys' | 'home_dir_found' | 'log_evidence'
}

export interface CreateCredentialRequest {
  cred_type: 'password' | 'private_key' | 'public_key'
  value: string
  fingerprint?: string | null
  key_type?: string | null
  comment?: string | null
}

export interface CreateCredentialLinkRequest {
  credential_id: string
  host_id: string
  host_user_id?: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source?: string | null
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
  timestamp?: string | null
  raw_line?: string | null
  source_file: string
}
