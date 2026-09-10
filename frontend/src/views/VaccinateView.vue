<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { petsApi, vaccinesApi, vaccinationsApi, inventoryApi } from '../api'
import type { Pet, Vaccination, Vaccine, VaccineBatch } from '../api/types'
import { SPECIES_EMOJI } from '../utils/format'

const route = useRoute()
const router = useRouter()

const pets = ref<Pet[]>([])
const vaccines = ref<Vaccine[]>([])
const records = ref<Vaccination[]>([])
const batches = ref<VaccineBatch[]>([])
const saving = ref(false)

const SITES = ['颈部皮下', '肩胛间皮下', '右前肢皮下', '左后肢肌肉', '臀部肌肉']
const DOCTORS = ['王医生', '李医生', '周医生']

const form = reactive({
  pet_id: undefined as number | undefined,
  vaccine_id: undefined as number | undefined,
  vacc_date: dayjs().format('YYYY-MM-DD'),
  batch_id: undefined as number | undefined,
  site: SITES[0],
  doctor: DOCTORS[0],
  reaction_level: '无',
  reaction_detail: '',
  next_due_date: '',
  auto_due: true,
  note: '',
})

const selectedPet = computed(() => pets.value.find(p => p.id === form.pet_id))
const selectedVac = computed(() => vaccines.value.find(v => v.id === form.vaccine_id))
const selectedBatch = computed(() => batches.value.find(b => b.id === form.batch_id))

// 接种日期不可选未来；手动下次接种日期不可早于本次接种日期
const disableFutureDate = (d: Date) => dayjs(d).isAfter(dayjs(), 'day')
const disableBeforeVaccDate = (d: Date) =>
  form.vacc_date ? dayjs(d).isBefore(dayjs(form.vacc_date), 'day') : false

const applicableVaccines = computed(() => {
  const sp = selectedPet.value?.species
  if (!sp) return vaccines.value
  return vaccines.value.filter(v => v.species === '通用' || v.species === sp)
})

// 可选批次：与宠物物种匹配、未过期、库存大于零（usable 由后端实时计算）
const usableBatches = computed(() =>
  batches.value.filter(b => b.usable && b.vaccine_id === form.vaccine_id))

// 根据疫苗标准间隔自动计算下次到期日
watch([() => form.vacc_date, () => form.vaccine_id, () => form.auto_due], () => {
  if (form.auto_due && form.vacc_date && selectedVac.value) {
    form.next_due_date = dayjs(form.vacc_date)
      .add(selectedVac.value.interval_days, 'day').format('YYYY-MM-DD')
  }
})

async function loadBatches() {
  const sp = selectedPet.value?.species
  batches.value = await inventoryApi.batches({
    species: sp || undefined,
    usable: true,
  })
}

watch(() => form.pet_id, async (id) => {
  // 仅当已选疫苗不适用于新宠物时才清空（通用疫苗或同物种疫苗保留，
  // 从到期提醒跳转带入的疫苗因此不会被重置）
  const sp = pets.value.find(p => p.id === id)?.species
  const vac = vaccines.value.find(v => v.id === form.vaccine_id)
  if (sp && vac && vac.species !== '通用' && vac.species !== sp) {
    form.vaccine_id = undefined
    form.batch_id = undefined
  }
  // 带出该宠物上次接种医生习惯
  const last = records.value.find(r => r.pet_id === id)
  if (last) {
    form.doctor = last.doctor || form.doctor
  }
  await loadBatches()
})

// 切换疫苗时重新拉取该疫苗可用批次并清空已选批次
watch(() => form.vaccine_id, async () => {
  form.batch_id = undefined
  await loadBatches()
})

async function load() {
  ;[pets.value, vaccines.value, records.value] = await Promise.all([
    petsApi.list(), vaccinesApi.list(), vaccinationsApi.list(),
  ])
  if (route.query.pet) {
    form.pet_id = Number(route.query.pet)
  }
  if (route.query.vaccine) {
    form.vaccine_id = Number(route.query.vaccine)
  }
  await loadBatches()
}

async function submit() {
  if (!form.pet_id || !form.vaccine_id || !form.vacc_date) {
    ElMessage.warning('请选择宠物、疫苗和接种日期')
    return
  }
  if (!form.batch_id) {
    ElMessage.warning('请选择与宠物物种匹配、未过期且有库存的疫苗批次')
    return
  }
  if (dayjs(form.vacc_date).isAfter(dayjs(), 'day')) {
    ElMessage.warning('接种日期不得晚于今天')
    return
  }
  if (!form.auto_due && form.next_due_date
      && dayjs(form.next_due_date).isBefore(dayjs(form.vacc_date), 'day')) {
    ElMessage.warning('下次接种日期不得早于本次接种日期')
    return
  }
  const reaction = form.reaction_level === '无'
    ? '无'
    : `${form.reaction_level}：${form.reaction_detail || '详见病历'}`
  saving.value = true
  try {
    const res = await vaccinationsApi.create({
      pet_id: form.pet_id,
      vaccine_id: form.vaccine_id,
      vacc_date: form.vacc_date,
      batch_id: form.batch_id,
      site: form.site,
      doctor: form.doctor,
      adverse_reaction: reaction,
      next_due_date: form.auto_due ? undefined : form.next_due_date,
      note: form.note,
    })
    if (res.completed_plan_id) {
      ElMessage.success(`接种登记成功，批号 ${res.batch_no}，下次到期日 ${res.next_due_date}；`
        + `已自动完成随访计划 #${res.completed_plan_id}`)
    } else {
      ElMessage.success(`接种登记成功，批号 ${res.batch_no}，库存剩余 ${res.remaining} 支`)
    }
    records.value = await vaccinationsApi.list()
    await loadBatches()
    // 保留宠物、医生和疫苗，清空批次与反应备注
    form.batch_id = undefined
    form.reaction_level = '无'
    form.reaction_detail = ''
    form.note = ''
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-row :gutter="16">
    <!-- 登记表单 -->
    <el-col :span="10">
      <el-card class="card-shadow" header="💉 接种登记">
        <el-form :model="form" label-width="92px">
          <el-form-item label="宠物" required>
            <el-select v-model="form.pet_id" filterable placeholder="选择宠物"
                       style="width:100%">
              <el-option v-for="p in pets" :key="p.id"
                :label="`${SPECIES_EMOJI[p.species]||''} ${p.name}（${p.owner_name} ${p.owner_phone}）`"
                :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="疫苗" required>
            <el-select v-model="form.vaccine_id" placeholder="选择疫苗" style="width:100%">
              <el-option v-for="v in applicableVaccines" :key="v.id"
                :label="`${v.name}（间隔 ${v.interval_days} 天）`" :value="v.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="接种日期" required>
            <el-date-picker v-model="form.vacc_date" type="date"
                            value-format="YYYY-MM-DD" :disabled-date="disableFutureDate"
                            style="width:100%" />
          </el-form-item>
          <el-form-item label="库存批次" required>
            <el-select v-model="form.batch_id"
                       :placeholder="form.vaccine_id ? '选择批次' : '请先选择疫苗'"
                       :disabled="!form.vaccine_id" style="width:100%">
              <el-option v-for="b in usableBatches" :key="b.id"
                :label="`${b.batch_no}（剩 ${b.remaining} 支，有效期至 ${b.expiry_date}）`"
                :value="b.id">
                <span>{{ b.batch_no }}</span>
                <small style="color:#909399;margin-left:8px">
                  剩 {{ b.remaining }} 支 · {{ b.days_left <= 30 ? `临期(${b.days_left}天)` : `有效期至 ${b.expiry_date}` }}
                </small>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.vaccine_id && usableBatches.length === 0" label=" ">
            <el-alert type="error" :closable="false" show-icon
              title="该疫苗当前没有可用批次"
              description="请先在“疫苗库存”页登记或补充与宠物物种匹配、未过期且库存大于零的批次。" />
          </el-form-item>
          <el-form-item label="批号 / 厂家">
            <el-input :model-value="selectedBatch
              ? `${selectedBatch.batch_no} ｜ ${selectedBatch.manufacturer}`
              : '选择批次后自动带出'" readonly>
              <template #append>
                <el-button :icon="'Box'" @click="router.push('/inventory')" />
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="注射部位">
            <el-select v-model="form.site" style="width:100%">
              <el-option v-for="s in SITES" :key="s" :label="s" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="接种医生">
            <el-radio-group v-model="form.doctor">
              <el-radio-button v-for="d in DOCTORS" :key="d" :label="d" />
            </el-radio-group>
          </el-form-item>
          <el-form-item label="不良反应">
            <el-select v-model="form.reaction_level" style="width:100%">
              <el-option label="无" value="无" />
              <el-option label="轻微" value="轻微" />
              <el-option label="严重" value="严重" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.reaction_level !== '无'" label="反应描述">
            <el-input v-model="form.reaction_detail" type="textarea" :rows="2"
                      placeholder="如 注射部位红肿，次日消退" />
          </el-form-item>
          <el-form-item label="下次接种">
            <div style="display:flex;gap:8px;width:100%;align-items:center">
              <el-switch v-model="form.auto_due" active-text="自动" />
              <el-date-picker v-model="form.next_due_date" type="date"
                              value-format="YYYY-MM-DD" :disabled="form.auto_due"
                              :disabled-date="disableBeforeVaccDate"
                              style="flex:1" />
            </div>
            <small v-if="selectedVac && form.auto_due" style="color:#909399">
              按疫苗标准间隔 {{ selectedVac.interval_days }} 天自动计算
            </small>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.note" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="saving"
                       :icon="'Check'" @click="submit">确认登记</el-button>
            <el-button v-if="form.pet_id" @click="router.push(`/pets/${form.pet_id}`)">
              查看该宠物档案
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </el-col>

    <!-- 最近接种记录 -->
    <el-col :span="14">
      <el-card class="card-shadow" header="最近接种记录">
        <el-table :data="records.slice(0, 15)" size="small" stripe max-height="640">
          <el-table-column prop="vacc_date" label="日期" width="100" />
          <el-table-column label="宠物" width="90">
            <template #default="{ row }">
              <el-link type="primary" @click="router.push(`/pets/${row.pet_id}`)">
                {{ row.pet_name }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="vaccine_name" label="疫苗" min-width="100" />
          <el-table-column prop="batch_no" label="批号" width="90">
            <template #default="{ row }">{{ row.batch_no || '—' }}</template>
          </el-table-column>
          <el-table-column prop="site" label="部位" width="95" />
          <el-table-column prop="doctor" label="医生" width="70" />
          <el-table-column label="不良反应" width="85">
            <template #default="{ row }">
              <el-tag size="small"
                :type="row.reaction_level === 'none' ? 'success'
                  : row.reaction_level === 'severe' ? 'danger' : 'warning'">
                {{ row.reaction_level === 'none' ? '无'
                   : row.reaction_level === 'severe' ? '严重' : '轻微' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="next_due_date" label="下次到期" width="100" />
        </el-table>
      </el-card>
    </el-col>
  </el-row>
</template>
