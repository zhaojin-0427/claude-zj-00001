// 与后端字段对应的 TypeScript 类型定义

export interface Owner {
  id: number
  name: string
  phone: string
  address?: string
  pet_count?: number
  created_at?: string
}

export interface Pet {
  id: number
  owner_id: number
  name: string
  species: string
  breed?: string
  gender?: string
  birth_date?: string
  color?: string
  microchip?: string
  neutered: number
  owner_name?: string
  owner_phone?: string
  owner_address?: string
  vaccinations?: Vaccination[]
  antibodies?: AntibodyTest[]
  vaccine_status?: VaccineStatus[]
  followup_plans?: FollowupPlan[]
}

export interface Vaccine {
  id: number
  name: string
  species: string
  interval_days: number
  core: number
  description?: string
}

export interface Vaccination {
  id: number
  pet_id: number
  vaccine_id: number
  vaccine_name?: string
  vacc_date: string
  batch_no?: string
  manufacturer?: string
  site?: string
  doctor?: string
  adverse_reaction?: string
  reaction_level?: 'none' | 'mild' | 'severe'
  next_due_date?: string
  note?: string
  batch_id?: number | null
  pet_name?: string
  species?: string
  owner_name?: string
  owner_phone?: string
}

// 库存批次实时状态：normal 正常 / low 低库存 / expiring 临期 / expired 已过期
export type BatchStatus = 'normal' | 'low' | 'expiring' | 'expired'

export interface VaccineBatch {
  id: number
  vaccine_id: number
  batch_no: string
  manufacturer: string
  production_date: string
  expiry_date: string
  initial_quantity: number
  remaining: number
  total_inbound?: number
  warning_threshold: number
  operator: string
  note?: string
  created_at?: string
  vaccine_name?: string
  vaccine_species?: string
  interval_days?: number
  days_left: number
  status: BatchStatus
  usable: boolean
}

export interface BatchCreate {
  vaccine_id: number
  batch_no: string
  manufacturer: string
  production_date: string
  expiry_date: string
  quantity: number
  warning_threshold: number
  operator: string
  note?: string
}

// 库存流水类型：inbound 入库 / consume 接种消耗 / adjust 调整
export type StockTxnType = 'inbound' | 'consume' | 'adjust'

export interface InventoryTransaction {
  id: number
  batch_id: number
  vaccination_id?: number | null
  type: StockTxnType
  quantity: number
  delta: number
  remaining_after: number
  reason: string
  operator: string
  created_at: string
  batch_no?: string
  manufacturer?: string
  vaccine_name?: string
  vaccine_species?: string
  pet_name?: string
}

export interface AntibodyTest {
  id: number
  pet_id: number
  vaccine_id: number
  vaccine_name?: string
  test_date: string
  result: '阳性' | '弱阳性' | '阴性'
  titer?: number
  lab?: string
  note?: string
  pet_name?: string
}

export type VacStatusType = 'overdue' | 'due_soon' | 'valid' | 'none'

export interface VaccineStatus {
  vaccine_id: number
  vaccine_name: string
  interval_days: number
  status: VacStatusType | 'too_young'
  last_vacc_date: string | null
  next_due_date: string | null
}

export interface ReminderItem extends VaccineStatus {
  pet_id: number
  pet_name: string
  species: string
  owner_name: string
  owner_phone: string
  days_left: number | null
}

// 随访计划状态：待确认 / 已确认 / 已完成 / 已取消
export type FollowupStatus = 'pending' | 'confirmed' | 'completed' | 'cancelled'

export interface FollowupPlan {
  id: number
  pet_id: number
  vaccine_id: number
  plan_date: string
  assignee: string
  note?: string
  status: FollowupStatus
  created_at?: string
  updated_at?: string
  pet_name?: string
  species?: string
  owner_name?: string
  owner_phone?: string
  vaccine_name?: string
}

export interface FollowupPlanCreate {
  pet_id: number
  vaccine_id: number
  plan_date: string
  assignee: string
  note?: string
}

export interface CoverageRow {
  vaccine_id: number
  vaccine_name: string
  species: string
  applicable: number
  ever_vaccinated: number
  valid: number
  overdue: number
  coverage_rate: number
  ever_rate: number
}

export interface Stats {
  pet_count: number
  owner_count: number
  vaccination_count: number
  antibody_test_count: number
  overall_coverage_rate: number
  coverage: CoverageRow[]
  adverse: {
    total: number
    mild: number
    severe: number
    reaction_count: number
    rate: number
    severe_rate: number
  }
  overdue: {
    applicable: number
    overdue: number
    never: number
    unvaccinated: number
    rate: number
  }
  antibody: {
    items: {
      vaccine_name: string
      total: number
      positive: number
      weak: number
      negative: number
      positive_rate: number
    }[]
    total: number
    positive: number
    weak: number
    negative: number
    positive_rate: number
  }
  monthly: { month: string; cnt: number }[]
  species_dist: { species: string; cnt: number }[]
  followup: {
    total: number
    due_in_7_days: number
    completed: number
    pending: number
    confirmed: number
    cancelled: number
    completion_rate: number
  }
  recent_reactions: {
    vacc_date: string
    pet_name: string
    vaccine_name: string
    adverse_reaction: string
    doctor: string
  }[]
  inventory: {
    batch_count: number
    stock_total: number
    stock_valid: number
    expiring_soon_qty: number
    expiring_soon_batches: number
    low_batch_count: number
    expired_batch_count: number
    month_consumed: number
    month_consume_times: number
  }
}
