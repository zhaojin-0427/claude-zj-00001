<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { remindersApi } from '../api'
import type { ReminderItem } from '../api/types'
import { daysText, SPECIES_EMOJI, STATUS_META } from '../utils/format'

const router = useRouter()
const loading = ref(false)
const items = ref<ReminderItem[]>([])
const allItems = ref<ReminderItem[]>([])
const status = ref('')
const species = ref('')
const q = ref('')

async function load() {
  loading.value = true
  try {
    items.value = await remindersApi.list({
      status: status.value, species: species.value, q: q.value,
    })
  } finally {
    loading.value = false
  }
}

const counts = computed(() => {
  const c = { overdue: 0, due_soon: 0, valid: 0, none: 0 }
  for (const i of allItems.value) {
    if (i.status in c) (c as any)[i.status]++
  }
  return c
})

const cards = computed(() => [
  { key: 'overdue', label: '已逾期未接种', value: counts.value.overdue,
    color: '#f56c6c', icon: 'WarningFilled' },
  { key: 'due_soon', label: '30天内到期', value: counts.value.due_soon,
    color: '#e6a23c', icon: 'BellFilled' },
  { key: 'none', label: '从未接种', value: counts.value.none,
    color: '#909399', icon: 'QuestionFilled' },
  { key: 'valid', label: '免疫有效', value: counts.value.valid,
    color: '#67c23a', icon: 'CircleCheckFilled' },
])

function rowType(row: ReminderItem) {
  return row.status === 'overdue' ? 'danger-row'
    : row.status === 'due_soon' ? 'warn-row' : ''
}

function callPhone(phone: string) {
  navigator.clipboard?.writeText(phone)
}

onMounted(async () => {
  allItems.value = await remindersApi.list({})
  items.value = allItems.value
})
</script>

<template>
  <el-row :gutter="16" style="margin-bottom:16px">
    <el-col v-for="c in cards" :key="c.key" :span="6">
      <div class="stat-card"
           :style="{ borderTop: `3px solid ${c.color}`, cursor: 'pointer' }"
           @click="status = status === c.key ? '' : c.key; load()">
        <div class="icon-box" :style="{ background: c.color }">
          <el-icon :size="26"><component :is="c.icon" /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ c.value }}</div>
          <div class="stat-label">{{ c.label }}</div>
        </div>
      </div>
    </el-col>
  </el-row>

  <div class="filter-bar">
    <el-radio-group v-model="status" @change="load">
      <el-radio-button label="">全部</el-radio-button>
      <el-radio-button label="overdue">已逾期</el-radio-button>
      <el-radio-button label="due_soon">即将到期</el-radio-button>
      <el-radio-button label="none">从未接种</el-radio-button>
      <el-radio-button label="valid">免疫有效</el-radio-button>
    </el-radio-group>
    <el-select v-model="species" placeholder="物种" clearable style="width:110px"
               @change="load">
      <el-option label="犬" value="犬" />
      <el-option label="猫" value="猫" />
      <el-option label="兔" value="兔" />
    </el-select>
    <el-input v-model="q" placeholder="宠物/主人/手机号" clearable style="width:200px"
              @keyup.enter="load" @clear="load" />
  </div>

  <el-table :data="items" v-loading="loading" class="card-shadow"
            :row-class-name="rowType">
    <el-table-column label="状态" width="110">
      <template #default="{ row }">
        <el-tag :type="(STATUS_META[row.status].type as any)">
          {{ STATUS_META[row.status].label }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="距到期" width="120">
      <template #default="{ row }">
        <el-text :type="row.status === 'overdue' ? 'danger'
                  : row.status === 'due_soon' ? 'warning' : 'success'" tag="b">
          {{ row.status === 'none' ? '—' : daysText(row.days_left) }}
        </el-text>
      </template>
    </el-table-column>
    <el-table-column label="宠物" min-width="130">
      <template #default="{ row }">
        <span style="font-size:18px">{{ SPECIES_EMOJI[row.species] || '🐾' }}</span>
        <el-link type="primary" style="margin-left:6px"
                 @click="router.push(`/pets/${row.pet_id}`)">
          {{ row.pet_name }}
        </el-link>
        <el-tag size="small" type="info" style="margin-left:6px">{{ row.species }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="vaccine_name" label="待种疫苗" min-width="150" />
    <el-table-column prop="owner_name" label="主人" width="90" />
    <el-table-column label="联系电话" width="150">
      <template #default="{ row }">
        <el-link type="primary" :underline="false" @click="callPhone(row.owner_phone)">
          📞 {{ row.owner_phone }}
        </el-link>
      </template>
    </el-table-column>
    <el-table-column prop="last_vacc_date" label="上次接种" width="110">
      <template #default="{ row }">{{ row.last_vacc_date || '—' }}</template>
    </el-table-column>
    <el-table-column prop="next_due_date" label="应种日期" width="110">
      <template #default="{ row }">
        <span :style="row.status==='overdue' ? 'color:#f56c6c;font-weight:600' : ''">
          {{ row.next_due_date || '—' }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="130" fixed="right">
      <template #default="{ row }">
        <el-button size="small" type="primary"
                   @click="router.push({ path: '/vaccinate', query: { pet: row.pet_id } })">
          登记接种
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
:deep(.danger-row) { background: #fef0f0 !important; }
:deep(.warn-row) { background: #fdf6ec !important; }
</style>
