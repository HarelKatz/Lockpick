import type { CredentialLink } from '../types'

export const RELATIONSHIP_TYPES: { value: CredentialLink['relationship_type']; label: string }[] = [
  { value: 'found_on_disk', label: 'Found on disk' },
  { value: 'authorized_key', label: 'Authorized key (grants access)' },
  { value: 'accepted_password', label: 'Accepted password' },
  { value: 'used_in_connection', label: 'Used in connection' },
]
