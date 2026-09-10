<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { inventoryApi, vaccinesApi } from '../api'
import type { Vaccine, VaccineBatch, BatchCreate, InventoryTransaction } from '../api/types'
import { BATCH_STATUS_META, SPECIES_EMOJI, STOCK_TXN_META } from '../utils/format'

const loading = ref(false)
// allBatches：不含状态过滤的全量（疫苗/批号过滤仍生效），汇总卡始终统计它；
// batches：在全量基础上再按状态筛选，仅供表格展示。这样点击状态卡不会改写卡上数量。
const allBatches = ref<VaccineBatch[]>([])
const batches = ref<VaccineBatch[]>([])
const vaccines = ref<Vaccine[]>([])

const filters = reactive({
  vaccine_id: '' as number | '',
  batch_no: '',
  status: '',
})

// ---------- 状态统计（始终基于未按状态过滤的全量） ----------
const statusCounts = computed(() => {
  const c = { normal: 0, low: 0, expiring: 0, expired: 0 }
  for (const b of allBatches.value) c[b.status]++
  return c
})

const summaryCards = computed(() => [
  { key: 'normal', label: '正常批次', value: statusCounts.value.normal, color: '#67c23a' },
  { key: 'low', label: '低库存批次', value: statusCounts.value.low, color: '#409eff' },
  { key: 'expiring', label: '临期批次', value: statusCounts.value.expiring, color: '#e6a23c' },
  { key: 'expired', label: '已过期批次', value: statusCounts.value.expired, color: '#f56c6c' },
])

async function load() {
  loading.value = true
  try {
    // 全量拉取（仅疫苗/批号过滤），状态实时计算在后端完成
    allBatches.value = await inventoryApi.batches({
      vaccine_id: filters.vaccine_id || undefined,
      batch_no: filters.batch_no || undefined,
    })
    // 表格数据再按状态筛选；切换状态卡无需重新请求，卡上数量保持稳定
    batches.value = filters.status
      ? allBatches.value.filter(b => b.status === filters.status)
      : allBatches.value
  } finally {
    loading.value = false
  }
}

// ---------- 登记新批次 ----------
const OPERATORS = ['库管小陈', '王医生', '李医生', '周医生']

function emptyBatchForm(): BatchCreate {
  return {
    vaccine_id: undefined as unknown as number,
    batch_no: '',
    manufacturer: '',
    production_date: dayjs().subtract(60, 'day').format('YYYY-MM-DD'),
    expiry_date: dayjs().add(365, 'day').format('YYYY-MM-DD'),
    quantity: 50,
    warning_threshold: 10,
    operator: OPERATORS[0],
    note: '',
  }
}

const createDialog = ref(false)
const createSaving = ref(false)
const batchForm = reactive<BatchCreate>(emptyBatchForm())

function openCreate() {
  Object.assign(batchForm, emptyBatchForm())
  createDialog.value = true
}

const createFormRef = ref()
const batchRules = {
  vaccine_id: [{ required: true, message: '请选择疫苗', trigger: 'change' }],
  batch_no: [{ required: true, message: '请输入批号', trigger: 'blur' }],
  manufacturer: [{ required: true, message: '请输入生产厂家', trigger: 'blur' }],
  production_date: [{ required: true, message: '请选择生产日期', trigger: 'change' }],
  expiry_date: [{ required: true, message: '请选择有效期', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入入库数量', trigger: 'blur' }],
  operator: [{ required: true, message: '请选择操作人', trigger: 'change' }],
}

function isPositiveInt(v: unknown) {
  return typeof v === 'number' && Number.isInteger(v) && v > 0
}

async function submitCreate() {
  await createFormRef.value?.validate()
  if (!isPositiveInt(batchForm.quantity)) {
    ElMessage.warning('入库数量必须为正整数')
    return
  }
  if (batchForm.warning_threshold < 0
      || !Number.isInteger(batchForm.warning_threshold)) {
    ElMessage.warning('预警阈值必须为非负整数')
    return
  }
  if (dayjs(batchForm.expiry_date).isBefore(dayjs(batchForm.production_date), 'day')) {
    ElMessage.warning('有效期不得早于生产日期')
    return
  }
  createSaving.value = true
  try {
    await inventoryApi.createBatch({ ...batchForm })
    ElMessage.success(`批次 ${batchForm.batch_no} 登记成功，已入库 ${batchForm.quantity} 支`)
    createDialog.value = false
    load()
  } finally {
    createSaving.value = false
  }
}

// ---------- 入库补充 / 库存调整 ----------
const opDialog = ref(false)
const opSaving = ref(false)
const opMode = ref<'restock' | 'adjust'>('restock')
const opTarget = ref<VaccineBatch | null>(null)
const opForm = reactive({ quantity: 10, change: 0, reason: '', operator: OPERATORS[0] })

function openOp(row: VaccineBatch, mode: 'restock' | 'adjust') {
  opTarget.value = row
  opMode.value = mode
  opForm.quantity = 10
  opForm.change = 0
  opForm.reason = ''
  opForm.operator = OPERATORS[0]
  opDialog.value = true
}

const opTitle = computed(() => {
  const b = opTarget.value
  if (!b) return ''
  return opMode.value === 'restock'
    ? `入库补充：${b.vaccine_name} / ${b.batch_no}`
    : `库存调整：${b.vaccine_name} / ${b.batch_no}`
})

const afterAdjust = computed(() =>
  opTarget.value ? opTarget.value.remaining + Number(opForm.change || 0) : 0)

async function submitOp() {
  const b = opTarget.value
  if (!b) return
  if (!opForm.reason.trim()) {
    ElMessage.warning(opMode.value === 'restock' ? '请填写入库原因' : '请填写调整原因')
    return
  }
  if (opMode.value === 'restock') {
    if (!isPositiveInt(opForm.quantity)) {
      ElMessage.warning('入库数量必须为正整数')
      return
    }
    opSaving.value = true
    try {
      const res = await inventoryApi.restock(b.id, {
        quantity: opForm.quantity, reason: opForm.reason.trim(),
        operator: opForm.operator,
      })
      ElMessage.success(`入库成功，当前剩余 ${res.remaining} 支`)
      opDialog.value = false
      load()
    } finally {
      opSaving.value = false
    }
  } else {
    if (!Number.isInteger(opForm.change) || opForm.change === 0) {
      ElMessage.warning('调整数量必须为非零整数（盘盈填正、盘亏填负）')
      return
    }
    if (afterAdjust.value < 0) {
      ElMessage.warning(`调整后库存为负（当前剩余 ${b.remaining}），已拒绝`)
      return
    }
    opSaving.value = true
    try {
      const res = await inventoryApi.adjust(b.id, {
        change: opForm.change, reason: opForm.reason.trim(),
        operator: opForm.operator,
      })
      ElMessage.success(`调整成功，当前剩余 ${res.remaining} 支`)
      opDialog.value = false
      load()
    } finally {
      opSaving.value = false
    }
  }
}

// ---------- 流水抽屉 ----------
const txnDrawer = ref(false)
const txnLoading = ref(false)
const txnRows = ref<InventoryTransaction[]>([])
const txnTitle = ref('全部库存流水')
const txnTypeFilter = ref('')
// 当前抽屉锁定的批次；undefined 表示全库流水。独立保存，避免被其他对话框目标污染
const txnBatchId = ref<number | undefined>(undefined)

async function openTxns(row?: VaccineBatch) {
  txnDrawer.value = true
  txnTypeFilter.value = ''
  txnBatchId.value = row?.id
  txnTitle.value = row ? `批次流水：${row.vaccine_name} / ${row.batch_no}` : '全部库存流水'
  await loadTxns()
}

async function loadTxns() {
  txnLoading.value = true
  try {
    txnRows.value = await inventoryApi.transactions({
      batch_id: txnBatchId.value,
      type: (txnTypeFilter.value || '') as InventoryTransaction['type'] | '',
    })
  } finally {
    txnLoading.value = false
  }
}

// 按当前 filters.status 在本地筛选表格（汇总卡数量不受影响）
function applyStatusFilter() {
  batches.value = filters.status
    ? allBatches.value.filter(b => b.status === filters.status)
    : allBatches.value
}

// 点击状态卡：同一张卡再点一次取消筛选
function toggleStatus(key: string) {
  filters.status = filters.status === key ? '' : key
  applyStatusFilter()
}

onMounted(async () => {
  vaccines.value = await vaccinesApi.list()
  await load()
})
</script>

<template>
  <div v-loading="loading">
    <!-- 状态汇总卡片（点击可筛选） -->
    <el-row :gutter="12" style="margin-bottom:14px">
      <el-col v-for="c in summaryCards" :key="c.key" :span="6">
        <div class="stat-card"
             :style="{ borderTop: `3px solid ${c.color}`,
                       cursor: 'pointer',
                       outline: filters.status === c.key ? `2px solid ${c.color}` : 'none' }"
             @click="toggleStatus(c.key)">
          <div style="font-size:28px;font-weight:700" :style="{ color: c.color }">
            {{ c.value }}
          </div>
          <div style="color:#606266">{{ c.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-card class="card-shadow">
      <!-- 检索栏 -->
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:center">
        <el-select v-model="filters.vaccine_id" placeholder="疫苗（全部）" clearable
                   filterable style="width:200px" @change="load">
          <el-option v-for="v in vaccines" :key="v.id"
            :label="`${SPECIES_EMOJI[v.species] || ''} ${v.name}`" :value="v.id" />
        </el-select>
        <el-input v-model="filters.batch_no" placeholder="批号关键字" clearable
                  style="width:180px" @keyup.enter="load" @clear="load" />
        <el-select v-model="filters.status" placeholder="状态（全部）" clearable
                   style="width:150px" @change="applyStatusFilter">
          <el-option v-for="(m, k) in BATCH_STATUS_META" :key="k"
                     :label="m.label" :value="k" />
        </el-select>
        <el-button type="primary" :icon="'Search'" @click="load">检索</el-button>
        <div style="flex:1"></div>
        <el-button :icon="'List'" @click="openTxns()">库存流水</el-button>
        <el-button type="success" :icon="'Plus'" @click="openCreate">登记新批次</el-button>
      </div>

      <el-table :data="batches" size="small" stripe max-height="600">
        <el-table-column label="疫苗" min-width="150">
          <template #default="{ row }">
            {{ SPECIES_EMOJI[row.vaccine_species] || '' }} {{ row.vaccine_name }}
          </template>
        </el-table-column>
        <el-table-column prop="batch_no" label="批号" width="110" />
        <el-table-column prop="manufacturer" label="厂家" min-width="130" />
        <el-table-column prop="production_date" label="生产日期" width="105" />
        <el-table-column label="有效期" width="120">
          <template #default="{ row }">
            <span :style="{ color: row.days_left < 0 ? '#f56c6c'
                : row.days_left <= 30 ? '#e6a23c' : undefined }">
              {{ row.expiry_date }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="剩余/累计入库" width="105" align="center">
          <template #default="{ row }">
            <strong :style="{ color: row.remaining === 0 ? '#909399' : undefined }">
              {{ row.remaining }}
            </strong>
            / {{ row.total_inbound ?? row.initial_quantity }}
          </template>
        </el-table-column>
        <el-table-column prop="warning_threshold" label="预警阈值" width="80" align="center" />
        <el-table-column label="状态" width="92" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="dark"
              :style="{ backgroundColor: BATCH_STATUS_META[row.status].color,
                        borderColor: BATCH_STATUS_META[row.status].color }">
              {{ BATCH_STATUS_META[row.status].label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="90" />
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small"
                       :disabled="row.status === 'expired'"
                       @click="openOp(row, 'restock')">入库补充</el-button>
            <el-button link type="warning" size="small"
                       @click="openOp(row, 'adjust')">库存调整</el-button>
            <el-button link type="info" size="small" @click="openTxns(row)">流水</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 登记新批次对话框 -->
    <el-dialog v-model="createDialog" title="登记疫苗库存批次" width="560px">
      <el-form ref="createFormRef" :model="batchForm" :rules="batchRules" label-width="92px">
        <el-form-item label="疫苗" prop="vaccine_id">
          <el-select v-model="batchForm.vaccine_id" filterable placeholder="选择疫苗"
                     style="width:100%">
            <el-option v-for="v in vaccines" :key="v.id"
                       :label="`${SPECIES_EMOJI[v.species] || ''} ${v.name}（${v.species}）`"
                       :value="v.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="批号" prop="batch_no">
          <el-input v-model="batchForm.batch_no" placeholder="如 B2026081501" />
        </el-form-item>
        <el-form-item label="生产厂家" prop="manufacturer">
          <el-input v-model="batchForm.manufacturer" placeholder="如 硕腾 Zoetis" />
        </el-form-item>
        <el-row :gutter="8">
          <el-col :span="12">
            <el-form-item label="生产日期" prop="production_date">
              <el-date-picker v-model="batchForm.production_date" type="date"
                              value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="有效期" prop="expiry_date">
              <el-date-picker v-model="batchForm.expiry_date" type="date"
                              value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="8">
          <el-col :span="12">
            <el-form-item label="入库数量" prop="quantity">
              <el-input-number v-model="batchForm.quantity" :min="1" :step="10"
                               style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预警阈值">
              <el-input-number v-model="batchForm.warning_threshold" :min="0"
                               style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="操作人" prop="operator">
          <el-select v-model="batchForm.operator" filterable allow-create
                     placeholder="选择或输入" style="width:100%">
            <el-option v-for="o in OPERATORS" :key="o" :label="o" :value="o" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="batchForm.note" type="textarea" :rows="2"
                    placeholder="如 冷链运输正常" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="createSaving" @click="submitCreate">
          确认登记
        </el-button>
      </template>
    </el-dialog>

    <!-- 入库补充 / 库存调整对话框 -->
    <el-dialog v-model="opDialog" :title="opTitle" width="460px">
      <el-alert v-if="opMode === 'adjust'" type="info" :closable="false"
        title="库存调整用于盘盈/盘耗等库存修正；日常入库请使用「入库补充」。"
        style="margin-bottom:12px" />
      <el-form label-width="92px">
        <el-form-item v-if="opTarget" label="当前剩余">
          <el-tag size="large">{{ opTarget.remaining }} 支</el-tag>
        </el-form-item>
        <el-form-item v-if="opMode === 'restock'" label="入库数量" required>
          <el-input-number v-model="opForm.quantity" :min="1" :step="5"
                           style="width:100%" />
        </el-form-item>
        <template v-else>
          <el-form-item label="调整数量" required>
            <el-input-number v-model="opForm.change" :step="1" style="width:100%" />
          </el-form-item>
          <el-form-item label="调整后结余">
            <el-tag size="large" :type="afterAdjust < 0 ? 'danger' : 'success'">
              {{ afterAdjust }} 支
            </el-tag>
          </el-form-item>
        </template>
        <el-form-item v-if="opMode === 'restock' && opTarget" label="入库后结余">
          <el-tag size="large" type="success">
            {{ opTarget.remaining + Number(opForm.quantity || 0) }} 支
          </el-tag>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-if="opMode === 'restock'" v-model="opForm.reason"
                    type="textarea" :rows="2" placeholder="如 供应商补货 / 退回再入库" />
          <el-input v-else v-model="opForm.reason" type="textarea" :rows="2"
                    placeholder="如 运输破损报损 -2 / 盘盈 +1" />
        </el-form-item>
        <el-form-item label="操作人" required>
          <el-select v-model="opForm.operator" filterable allow-create style="width:100%">
            <el-option v-for="o in OPERATORS" :key="o" :label="o" :value="o" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="opDialog = false">取消</el-button>
        <el-button :type="opMode === 'restock' ? 'success' : 'warning'"
                   :loading="opSaving" @click="submitOp">确认</el-button>
      </template>
    </el-dialog>

    <!-- 流水抽屉 -->
    <el-drawer v-model="txnDrawer" :title="txnTitle" size="60%">
      <div style="margin-bottom:10px">
        <el-radio-group v-model="txnTypeFilter" size="small"
                        @change="loadTxns()">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="inbound">入库</el-radio-button>
          <el-radio-button label="consume">消耗</el-radio-button>
          <el-radio-button label="adjust">调整</el-radio-button>
        </el-radio-group>
      </div>
      <el-table :data="txnRows" v-loading="txnLoading" size="small" stripe max-height="640">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="(STOCK_TXN_META[row.type].type as any)">
              {{ STOCK_TXN_META[row.type].label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="疫苗/批号" min-width="170">
          <template #default="{ row }">
            {{ row.vaccine_name }}<br />
            <small style="color:#909399">{{ row.batch_no }} · {{ row.manufacturer }}</small>
          </template>
        </el-table-column>
        <el-table-column label="变动" width="90" align="center">
          <template #default="{ row }">
            <span :style="{ color: row.delta > 0 ? '#67c23a' : '#f56c6c',
                            fontWeight: 600 }">
              {{ row.delta > 0 ? '+' : '' }}{{ row.delta }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remaining_after" label="结余" width="70" align="center" />
        <el-table-column prop="reason" label="原因" min-width="170" />
        <el-table-column prop="pet_name" label="消耗宠物" width="90">
          <template #default="{ row }">{{ row.pet_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="90" />
      </el-table>
    </el-drawer>
  </div>
</template>
