/**
 * API functions for Operations.
 */
import { api } from './client'
import type { Operation, CreateOperationRequest } from '../types'

export async function listOperations(): Promise<Operation[]> {
  return api.get<Operation[]>('/ops')
}

export async function getOperation(opId: string): Promise<Operation> {
  return api.get<Operation>(`/ops/${opId}`)
}

export async function createOperation(data: CreateOperationRequest): Promise<Operation> {
  return api.post<Operation>('/ops', data)
}

export async function deleteOperation(opId: string): Promise<void> {
  return api.delete(`/ops/${opId}`)
}
