/**
 * API functions for Hosts and HostIPs.
 */
import { api } from './client'
import type {
  Host,
  HostIP,
  HostUser,
  CreateHostRequest,
  UpdateHostRequest,
  CreateHostIPRequest,
  CreateHostUserRequest,
} from '../types'

export async function listHosts(opId: string): Promise<Host[]> {
  return api.get<Host[]>(`/ops/${opId}/hosts`)
}

export async function getHost(hostId: string): Promise<Host> {
  return api.get<Host>(`/hosts/${hostId}`)
}

export async function createHost(opId: string, data: CreateHostRequest): Promise<Host> {
  return api.post<Host>(`/ops/${opId}/hosts`, data)
}

export async function updateHost(hostId: string, data: UpdateHostRequest): Promise<Host> {
  return api.patch<Host>(`/hosts/${hostId}`, data)
}

export async function deleteHost(hostId: string): Promise<void> {
  return api.delete(`/hosts/${hostId}`)
}

export async function addHostIP(hostId: string, data: CreateHostIPRequest): Promise<HostIP> {
  return api.post<HostIP>(`/hosts/${hostId}/ips`, data)
}

export async function deleteHostIP(hostId: string, ipId: string): Promise<void> {
  return api.delete(`/hosts/${hostId}/ips/${ipId}`)
}

export async function listHostUsers(hostId: string): Promise<HostUser[]> {
  return api.get<HostUser[]>(`/hosts/${hostId}/users`)
}

export async function createHostUser(hostId: string, data: CreateHostUserRequest): Promise<HostUser> {
  return api.post<HostUser>(`/hosts/${hostId}/users`, data)
}

export async function deleteHostUser(hostId: string, userId: string): Promise<void> {
  return api.delete(`/hosts/${hostId}/users/${userId}`)
}
