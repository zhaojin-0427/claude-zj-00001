<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { followupsApi, remindersApi } from '../api'
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

// ---------- 批量生成随访计划 ----------
const DOCTORS = ['王医生', '李医生', '周医生']
const selected = ref<ReminderItem[]>([])
const planDialog = ref(false)
const planSaving = ref(false)
const planAssignee = ref(DOCTORS[0])
const planNote = ref('')
const planRows = ref<{ row: ReminderItem; plan_date: string }[]>([])

// 仅"已逾期 / 即将到期"的记录可勾选生成随访计划
const selectable = (row: ReminderItem) =>
  row.status === 'overdue' || row.status === 'due_soon'

function onSelectionChange(rows: ReminderItem[]) {
  selected.value = rows
}

function openPlanDialog() {
  if (!selected.value.length) {
    ElMessage.warning('请先勾选需要生成随访计划的记录')
    return
  }
  const today = dayjs().format('YYYY-MM-DD')
  // 默认计划日期：应种日期未过则取应种日期，已逾期则取今天
  planRows.value = selected.value.map(row => ({
    row,
    plan_date: row.next_due_date && row.next_due_date >= today
      ? row.next_due_date : today,
  }))
  planAssignee.value = DOCTORS[0]
  planNote.value = ''
  planDialog.value = true
}

const disablePastDate = (d: Date) => dayjs(d).isBefore(dayjs(), 'day')

async function submitPlans() {
  if (planRows.value.some(r => !r.plan_date)) {
    ElMessage.warning('请为每条记录选择计划日期')
    return
  }
  planSaving.value = true
  try {
    const res = await followupsApi.batchCreate(planRows.value.map(r => ({
      pet_id: r.row.pet_id,
      vaccine_id: r.row.vaccine_id,
      plan_date: r.plan_date,
      assignee: planAssignee.value,
      note: planNote.value,
    })))
    ElMessage.success(`已生成 ${res.created} 条随访计划，可在"随访计划"页查看`)
    planDialog.value = false
    selected.value = []
    load()
  } finally {
    planSaving.value = false
  }
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
    <el-button type="primary" :icon="'Plus'" :disabled="!selected.length"
               @click="openPlanDialog">
      批量生成随访计划{{ selected.length ? `（${selected.length}）` : '' }}
    </el-button>
    <el-button v-if="selected.length" link type="info"
               @click="router.push('/followups')">前往随访计划 →</el-button>
  </div>

  <el-table :data="items" v-loading="loading" class="card-shadow"
            :row-class-name="rowType" @selection-change="onSelectionChange">
    <el-table-column type="selection" width="45" :selectable="selectable" />
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
                   @click="router.push({ path: '/vaccinate',
                     query: { pet: row.pet_id, vaccine: row.vaccine_id } })">
          登记接种
        </el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- 批量生成随访计划 -->
  <el-dialog v-model="planDialog" title="批量生成随访计划" width="760px">
    <div style="display:flex;gap:12px;margin-bottom:14px;align-items:center">
      <span style="white-space:nowrap;color:#606266">负责人</span>
      <el-select v-model="planAssignee" style="width:140px">
        <el-option v-for="d in DOCTORS" :key="d" :label="d" :value="d" />
      </el-select>
      <span style="white-space:nowrap;color:#606266">备注</span>
      <el-input v-model="planNote" placeholder="统一备注，如 电话随访提醒（可选）" />
    </div>
    <el-table :data="planRows" size="small" max-height="380">
      <el-table-column label="宠物" width="110">
        <template #default="{ row }">
          {{ SPECIES_EMOJI[row.row.species] || '🐾' }} {{ row.row.pet_name }}
        </template>
      </el-table-column>
      <el-table-column label="疫苗" min-width="130">
        <template #default="{ row }">{{ row.row.vaccine_name }}</template>
      </el-table-column>
      <el-table-column label="应种日期" width="105">
        <template #default="{ row }">{{ row.row.next_due_date || '—' }}</template>
      </el-table-column>
      <el-table-column label="计划日期" width="170">
        <template #default="{ row }">
          <el-date-picker v-model="row.plan_date" type="date" size="small"
                          value-format="YYYY-MM-DD" :disabled-date="disablePastDate"
                          style="width:150px" />
        </template>
      </el-table-column>
    </el-table>
    <el-alert type="info" :closable="false" style="margin-top:12px"
              title="同一宠物同一疫苗仅允许一条未结束的随访计划；任一记录校验失败将取消全部创建" />
    <template #footer>
      <el-button @click="planDialog = false">取消</el-button>
      <el-button type="primary" :loading="planSaving" @click="submitPlans">
        生成 {{ planRows.length }} 条计划
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
:deep(.danger-row) { background: #fef0f0 !important; }
:deep(.warn-row) { background: #fdf6ec !important; }
</style>
