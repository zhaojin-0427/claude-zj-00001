import http from './http'
import type {
  Owner, Pet, Vaccine, Vaccination, AntibodyTest, ReminderItem, Stats,
  FollowupPlan, FollowupPlanCreate, VaccineBatch, BatchCreate,
  InventoryTransaction, StockTxnType,
} from './types'

export const ownersApi = {
  list: (q = '') => http.get<Owner[]>('/owners', { params: { q } }).then(r => r.data),
  create: (data: Partial<Owner>) => http.post('/owners', data).then(r => r.data),
}

export const petsApi = {
  list: (params: { species?: string; q?: string } = {}) =>
    http.get<Pet[]>('/pets', { params }).then(r => r.data),
  detail: (id: number) => http.get<Pet>(`/pets/${id}`).then(r => r.data),
  create: (data: Partial<Pet>) => http.post('/pets', data).then(r => r.data),
}

export const vaccinesApi = {
  list: (species = '') =>
    http.get<Vaccine[]>('/vaccines', { params: { species } }).then(r => r.data),
}

export const vaccinationsApi = {
  list: (petId?: number) =>
    http.get<Vaccination[]>('/vaccinations', { params: { pet_id: petId } })
      .then(r => r.data),
  create: (data: Partial<Vaccination>) =>
    http.post('/vaccinations', data).then(r => r.data),
}

export const antibodiesApi = {
  list: (petId?: number) =>
    http.get<AntibodyTest[]>('/antibodies', { params: { pet_id: petId } })
      .then(r => r.data),
  create: (data: Partial<AntibodyTest>) =>
    http.post('/antibodies', data).then(r => r.data),
}

export const remindersApi = {
  list: (params: { status?: string; species?: string; q?: string } = {}) =>
    http.get<ReminderItem[]>('/reminders', { params }).then(r => r.data),
}

export const followupsApi = {
  list: (params: {
    status?: string; date_from?: string; date_to?: string;
    q?: string; pet_id?: number
  } = {}) => http.get<FollowupPlan[]>('/followup-plans', { params }).then(r => r.data),
  batchCreate: (items: FollowupPlanCreate[]) =>
    http.post<{ created: number; ids: number[] }>('/followup-plans/batch', { items })
      .then(r => r.data),
  confirm: (id: number) =>
    http.post(`/followup-plans/${id}/confirm`).then(r => r.data),
  reschedule: (id: number, data: { plan_date: string; assignee?: string; note?: string }) =>
    http.post(`/followup-plans/${id}/reschedule`, data).then(r => r.data),
  cancel: (id: number) =>
    http.post(`/followup-plans/${id}/cancel`).then(r => r.data),
}

export const statsApi = {
  get: () => http.get<Stats>('/stats').then(r => r.data),
}

export const inventoryApi = {
  batches: (params: {
    vaccine_id?: number | string
    batch_no?: string
    status?: string
    species?: string
    usable?: boolean
  } = {}) =>
    http.get<VaccineBatch[]>('/inventory/batches', {
      params: {
        vaccine_id: params.vaccine_id,
        batch_no: params.batch_no,
        status: params.status,
        species: params.species,
        usable: params.usable === undefined ? undefined : (params.usable ? 1 : 0),
      },
    }).then(r => r.data),
  createBatch: (data: BatchCreate) =>
    http.post<{ id: number; remaining: number }>('/inventory/batches', data)
      .then(r => r.data),
  restock: (id: number, data: { quantity: number; reason: string; operator: string }) =>
    http.post<{ id: number; remaining: number }>(
      `/inventory/batches/${id}/restock`, data).then(r => r.data),
  adjust: (id: number, data: { change: number; reason: string; operator: string }) =>
    http.post<{ id: number; remaining: number }>(
      `/inventory/batches/${id}/adjust`, data).then(r => r.data),
  transactions: (params: { batch_id?: number; type?: StockTxnType | '' } = {}) =>
    http.get<InventoryTransaction[]>('/inventory/transactions', { params })
      .then(r => r.data),
}
