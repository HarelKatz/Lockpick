/**
 * API functions for Hosts and HostIPs.
 */
import { api } from './client'
import type {
  Host,
  HostIP,
  CreateHostRequest,
  CreateHostIPRequest,
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

export async function updateHost(hostId: string, data: Partial<CreateHostRequest>): Promise<Host> {
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
