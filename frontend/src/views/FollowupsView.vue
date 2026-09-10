<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { followupsApi } from '../api'
import type { FollowupPlan } from '../api/types'
import { FOLLOWUP_STATUS_META, SPECIES_EMOJI } from '../utils/format'

const router = useRouter()
const loading = ref(false)
const items = ref<FollowupPlan[]>([])
const allItems = ref<FollowupPlan[]>([])
const status = ref('')
const dateRange = ref<[string, string] | null>(null)
const q = ref('')

async function load() {
  loading.value = true
  try {
    items.value = await followupsApi.list({
      status: status.value,
      date_from: dateRange.value?.[0] || '',
      date_to: dateRange.value?.[1] || '',
      q: q.value,
    })
  } finally {
    loading.value = false
  }
}

const counts = computed(() => {
  const c = { pending: 0, confirmed: 0, completed: 0, cancelled: 0 }
  for (const i of allItems.value) {
    if (i.status in c) (c as any)[i.status]++
  }
  return c
})

const cards = computed(() => [
  { key: 'pending', label: '待确认', value: counts.value.pending,
    color: '#e6a23c', icon: 'Clock' },
  { key: 'confirmed', label: '已确认', value: counts.value.confirmed,
    color: '#409eff', icon: 'CircleCheck' },
  { key: 'completed', label: '已完成', value: counts.value.completed,
    color: '#67c23a', icon: 'CircleCheckFilled' },
  { key: 'cancelled', label: '已取消', value: counts.value.cancelled,
    color: '#909399', icon: 'CircleCloseFilled' },
])

const isOpen = (row: FollowupPlan) =>
  row.status === 'pending' || row.status === 'confirmed'

async function confirmPlan(row: FollowupPlan) {
  await followupsApi.confirm(row.id)
  ElMessage.success(`已确认 ${row.pet_name} 的 ${row.vaccine_name} 随访计划`)
  refresh()
}

async function cancelPlan(row: FollowupPlan) {
  try {
    await ElMessageBox.confirm(
      `确定取消 ${row.pet_name} 的 ${row.vaccine_name} 随访计划（${row.plan_date}）吗？`,
      '取消随访计划',
      { type: 'warning', confirmButtonText: '确定取消', cancelButtonText: '再想想' },
    )
  } catch {
    return  // 用户放弃取消
  }
  await followupsApi.cancel(row.id)
  ElMessage.success('随访计划已取消')
  refresh()
}

// ---------- 改期 ----------
const rescheduleDialog = ref(false)
const rescheduleSaving = ref(false)
const editing = ref<FollowupPlan | null>(null)
const editForm = ref({ plan_date: '', assignee: '', note: '' })
const disablePastDate = (d: Date) => dayjs(d).isBefore(dayjs(), 'day')

function openReschedule(row: FollowupPlan) {
  editing.value = row
  editForm.value = {
    plan_date: row.plan_date,
    assignee: row.assignee,
    note: row.note || '',
  }
  rescheduleDialog.value = true
}

async function submitReschedule() {
  if (!editForm.value.plan_date) {
    ElMessage.warning('请选择新的计划日期')
    return
  }
  rescheduleSaving.value = true
  try {
    await followupsApi.reschedule(editing.value!.id, { ...editForm.value })
    ElMessage.success('随访计划已改期')
    rescheduleDialog.value = false
    refresh()
  } finally {
    rescheduleSaving.value = false
  }
}

async function refresh() {
  await load()
  allItems.value = await followupsApi.list({})
}

onMounted(refresh)
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
      <el-radio-button label="pending">待确认</el-radio-button>
      <el-radio-button label="confirmed">已确认</el-radio-button>
      <el-radio-button label="completed">已完成</el-radio-button>
      <el-radio-button label="cancelled">已取消</el-radio-button>
    </el-radio-group>
    <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                    start-placeholder="计划日期起" end-placeholder="计划日期止"
                    style="width:260px" @change="load" />
    <el-input v-model="q" placeholder="宠物/主人/手机号" clearable style="width:200px"
              @keyup.enter="load" @clear="load" />
    <el-button :icon="'Search'" @click="load">查询</el-button>
  </div>

  <el-table :data="items" v-loading="loading" class="card-shadow">
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="(FOLLOWUP_STATUS_META[row.status].type as any)">
          {{ FOLLOWUP_STATUS_META[row.status].label }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="plan_date" label="计划日期" width="110" sortable />
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
    <el-table-column prop="vaccine_name" label="疫苗" min-width="130" />
    <el-table-column prop="owner_name" label="主人" width="90" />
    <el-table-column prop="owner_phone" label="联系电话" width="130" />
    <el-table-column prop="assignee" label="负责人" width="90" />
    <el-table-column label="备注" min-width="140">
      <template #default="{ row }">{{ row.note || '—' }}</template>
    </el-table-column>
    <el-table-column label="最近更新" width="160">
      <template #default="{ row }">{{ row.updated_at || row.created_at }}</template>
    </el-table-column>
    <el-table-column label="操作" width="200" fixed="right">
      <template #default="{ row }">
        <template v-if="isOpen(row)">
          <el-button v-if="row.status === 'pending'" size="small" type="success"
                     @click="confirmPlan(row)">确认</el-button>
          <el-button size="small" type="primary" plain
                     @click="openReschedule(row)">改期</el-button>
          <el-button size="small" type="danger" plain
                     @click="cancelPlan(row)">取消</el-button>
        </template>
        <el-text v-else type="info" size="small">已结束</el-text>
      </template>
    </el-table-column>
  </el-table>

  <!-- 改期 -->
  <el-dialog v-model="rescheduleDialog" title="随访计划改期" width="440px">
    <el-form label-width="90px" v-if="editing">
      <el-form-item label="宠物/疫苗">
        <el-text>{{ editing.pet_name }} · {{ editing.vaccine_name }}</el-text>
      </el-form-item>
      <el-form-item label="计划日期" required>
        <el-date-picker v-model="editForm.plan_date" type="date"
                        value-format="YYYY-MM-DD" :disabled-date="disablePastDate"
                        style="width:100%" />
      </el-form-item>
      <el-form-item label="负责人">
        <el-input v-model="editForm.assignee" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="editForm.note" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="rescheduleDialog = false">取消</el-button>
      <el-button type="primary" :loading="rescheduleSaving"
                 @click="submitReschedule">保存</el-button>
    </template>
  </el-dialog>
</template>
