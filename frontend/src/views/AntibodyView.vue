<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { antibodiesApi, petsApi, vaccinesApi } from '../api'
import type { AntibodyTest, Pet, Vaccine } from '../api/types'
import { LineChart } from '../components/Charts'
import { RESULT_COLOR, SPECIES_EMOJI } from '../utils/format'

const pets = ref<Pet[]>([])
const vaccines = ref<Vaccine[]>([])
const tests = ref<AntibodyTest[]>([])
const petId = ref<number>()
const saving = ref(false)
const dialogVisible = ref(false)

const form = reactive({
  pet_id: undefined as number | undefined,
  vaccine_id: undefined as number | undefined,
  test_date: dayjs().format('YYYY-MM-DD'),
  result: '阳性',
  titer: undefined as number | undefined,
  lab: '',
  note: '',
})

const selectedPet = computed(() => pets.value.find(p => p.id === petId.value))
const petVaccines = computed(() => {
  const sp = selectedPet.value?.species
  if (!sp) return vaccines.value
  return vaccines.value.filter(v => v.species === '通用' || v.species === sp)
})

// 按疫苗分组并按日期排序
const grouped = computed(() => {
  const map = new Map<string, AntibodyTest[]>()
  for (const t of tests.value) {
    const arr = map.get(t.vaccine_name!) || []
    arr.push(t)
    map.set(t.vaccine_name!, arr)
  }
  return [...map.entries()].map(([name, list]) => ({
    name,
    list: [...list].sort((a, b) => a.test_date.localeCompare(b.test_date)),
  }))
})

const chartData = computed(() => ({
  labels: grouped.value[0]?.list.map(t => t.test_date) || [],
  datasets: grouped.value.map((g, i) => {
    const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#9b59b6']
    const c = colors[i % colors.length]
    return {
      label: g.name,
      data: g.list.map(t => t.titer ?? null),
      borderColor: c,
      backgroundColor: c + '22',
      tension: 0.3,
      spanGaps: true,
      pointRadius: 5,
      pointBackgroundColor: g.list.map(t => RESULT_COLOR[t.result] || c),
    }
  }),
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { position: 'bottom' as const },
    tooltip: {
      callbacks: {
        afterLabel(ctx: any) {
          const g = grouped.value[ctx.datasetIndex]
          return g?.list[ctx.dataIndex]?.result
        },
      },
    },
  },
  scales: {
    y: { title: { display: true, text: '抗体滴度' }, beginAtZero: true },
  },
}

const resultSummary = computed(() => {
  const s = { '阳性': 0, '弱阳性': 0, '阴性': 0 }
  for (const t of tests.value) s[t.result]++
  return s
})

async function loadPets() {
  pets.value = await petsApi.list()
  vaccines.value = await vaccinesApi.list()
  petId.value = pets.value[0]?.id
}

async function loadTests() {
  if (petId.value) tests.value = await antibodiesApi.list(petId.value)
}

watch(petId, loadTests)

function openDialog() {
  Object.assign(form, {
    pet_id: petId.value,
    vaccine_id: undefined,
    test_date: dayjs().format('YYYY-MM-DD'),
    result: '阳性', titer: undefined, lab: '', note: '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.pet_id || !form.vaccine_id || !form.test_date) {
    ElMessage.warning('请完善必填项')
    return
  }
  saving.value = true
  try {
    await antibodiesApi.create({ ...form, result: form.result as AntibodyTest['result'] })
    ElMessage.success('抗体检测记录已保存')
    dialogVisible.value = false
    await loadTests()
  } finally {
    saving.value = false
  }
}

onMounted(loadPets)
</script>

<template>
  <div class="filter-bar">
    <span style="font-weight:600">选择宠物：</span>
    <el-select v-model="petId" style="width:300px">
      <el-option v-for="p in pets" :key="p.id"
        :label="`${SPECIES_EMOJI[p.species]||'🐾'} ${p.name} · ${p.owner_name}（${p.breed || p.species}）`"
        :value="p.id" />
    </el-select>
    <div style="flex:1"></div>
    <el-button type="primary" :icon="'Plus'" @click="openDialog">登记抗体检测</el-button>
  </div>

  <template v-if="selectedPet">
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="(cnt, key) in resultSummary" :key="key">
        <div class="stat-card">
          <div class="icon-box"
               :style="{ background: RESULT_COLOR[key as string] }">
            {{ key === '阳性' ? '🛡️' : key === '弱阳性' ? '⚠️' : '❌' }}
          </div>
          <div>
            <div class="stat-value">{{ cnt }}</div>
            <div class="stat-label">{{ key }}次数</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="14">
        <el-card class="card-shadow"
          :header="`抗体滴度趋势 — ${selectedPet.name}`">
          <div v-if="grouped.length" style="height:380px">
            <LineChart :chart-data="chartData" :options="chartOptions" />
          </div>
          <el-empty v-else description="该宠物暂无抗体检测数据" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card class="card-shadow" header="检测明细">
          <el-table :data="[...tests].reverse()" size="small" max-height="380">
            <el-table-column prop="test_date" label="日期" width="100" />
            <el-table-column prop="vaccine_name" label="疫苗" min-width="100" />
            <el-table-column label="结果" width="75">
              <template #default="{ row }">
                <el-tag size="small" effect="plain"
                  :style="{ color: RESULT_COLOR[row.result],
                            borderColor: RESULT_COLOR[row.result] }">
                  {{ row.result }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="titer" label="滴度" width="65" />
            <el-table-column prop="lab" label="实验室" min-width="120" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </template>

  <el-dialog v-model="dialogVisible" title="登记抗体检测" width="480px">
    <el-form :model="form" label-width="82px">
      <el-form-item label="宠物">
        <el-select v-model="form.pet_id" style="width:100%" disabled>
          <el-option v-for="p in pets" :key="p.id"
                     :label="`${p.name}（${p.owner_name}）`" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="检测疫苗" required>
        <el-select v-model="form.vaccine_id" style="width:100%">
          <el-option v-for="v in petVaccines" :key="v.id" :label="v.name" :value="v.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="检测日期" required>
        <el-date-picker v-model="form.test_date" type="date"
                        value-format="YYYY-MM-DD" style="width:100%" />
      </el-form-item>
      <el-form-item label="结果" required>
        <el-radio-group v-model="form.result">
          <el-radio-button label="阳性" />
          <el-radio-button label="弱阳性" />
          <el-radio-button label="阴性" />
        </el-radio-group>
      </el-form-item>
      <el-form-item label="抗体滴度">
        <el-input-number v-model="form.titer" :min="0" :precision="2"
                         :step="0.5" style="width:100%" />
      </el-form-item>
      <el-form-item label="检测机构">
        <el-input v-model="form.lab" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>
