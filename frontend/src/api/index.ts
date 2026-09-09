import http from './http'
import type {
  Owner, Pet, Vaccine, Vaccination, AntibodyTest, ReminderItem, Stats,
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

export const statsApi = {
  get: () => http.get<Stats>('/stats').then(r => r.data),
}
