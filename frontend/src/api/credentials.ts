/**
 * API functions for Credentials and CredentialLinks.
 */
import { api } from './client'
import type {
  Credential,
  CredentialLink,
  CreateCredentialRequest,
  CreateCredentialLinkRequest,
  UpdateCredentialRequest,
  UpdateCredentialLinkRequest,
} from '../types'

export async function listCredentials(opId: string): Promise<Credential[]> {
  return api.get<Credential[]>(`/ops/${opId}/credentials`)
}

export async function createCredential(opId: string, data: CreateCredentialRequest): Promise<Credential> {
  return api.post<Credential>(`/ops/${opId}/credentials`, data)
}

export async function updateCredential(credId: string, data: UpdateCredentialRequest): Promise<Credential> {
  return api.patch<Credential>(`/credentials/${credId}`, data)
}

export async function deleteCredential(credId: string): Promise<void> {
  return api.delete(`/credentials/${credId}`)
}

export async function createCredentialLink(data: CreateCredentialLinkRequest): Promise<CredentialLink> {
  return api.post<CredentialLink>('/credential-links', data)
}

export async function listCredentialLinks(opId: string): Promise<CredentialLink[]> {
  return api.get<CredentialLink[]>(`/ops/${opId}/credential-links`)
}

export async function updateCredentialLink(linkId: string, data: UpdateCredentialLinkRequest): Promise<CredentialLink> {
  return api.patch<CredentialLink>(`/credential-links/${linkId}`, data)
}

export async function deleteCredentialLink(linkId: string): Promise<void> {
  return api.delete(`/credential-links/${linkId}`)
}
