<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { petsApi } from '../api'
import type { Pet } from '../api/types'
import { fmtDate, FOLLOWUP_STATUS_META, RESULT_COLOR, SPECIES_EMOJI, STATUS_META } from '../utils/format'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const pet = ref<Pet | null>(null)

onMounted(async () => {
  try {
    pet.value = await petsApi.detail(Number(route.params.id))
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading">
    <el-button :icon="'ArrowLeft'" link style="margin-bottom:12px"
               @click="router.push('/pets')">返回档案列表</el-button>

    <template v-if="pet">
      <!-- 基本信息 -->
      <el-card class="card-shadow" style="margin-bottom:16px">
        <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap">
          <el-avatar :size="72" style="background:#fdf6ec;font-size:40px">
            {{ SPECIES_EMOJI[pet.species] || '🐾' }}
          </el-avatar>
          <div style="flex:1;min-width:200px">
            <div style="display:flex;align-items:center;gap:10px">
              <span style="font-size:22px;font-weight:700">{{ pet.name }}</span>
              <el-tag>{{ pet.species }}</el-tag>
              <el-tag type="info">{{ pet.breed || '品种未填' }}</el-tag>
              <el-tag type="info" v-if="pet.neutered">已绝育</el-tag>
            </div>
            <el-descriptions :column="3" style="margin-top:10px" size="small">
              <el-descriptions-item label="性别">{{ pet.gender }}</el-descriptions-item>
              <el-descriptions-item label="出生日期">{{ fmtDate(pet.birth_date) }}</el-descriptions-item>
              <el-descriptions-item label="毛色">{{ pet.color || '—' }}</el-descriptions-item>
              <el-descriptions-item label="芯片号">{{ pet.microchip || '—' }}</el-descriptions-item>
              <el-descriptions-item label="主人">{{ pet.owner_name }}</el-descriptions-item>
              <el-descriptions-item label="联系电话">{{ pet.owner_phone }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <el-button type="primary" :icon="'Syringe'" size="large"
                     @click="router.push({ path: '/vaccinate', query: { pet: pet.id } })">
            登记接种
          </el-button>
        </div>
      </el-card>

      <!-- 各疫苗免疫状态 -->
      <el-card class="card-shadow" style="margin-bottom:16px" header="当前免疫状态">
        <el-row :gutter="12">
          <el-col v-for="s in pet.vaccine_status" :key="s.vaccine_id" :span="8">
            <el-alert
              :type="(STATUS_META[s.status].type as any)"
              :closable="false"
              style="margin-bottom:10px;align-items:flex-start">
              <template #title>
                <div style="display:flex;justify-content:space-between;width:100%;align-items:center">
                  <strong>{{ s.vaccine_name }}</strong>
                  <el-tag size="small" :type="(STATUS_META[s.status].type as any)">
                    {{ STATUS_META[s.status].label }}
                  </el-tag>
                </div>
                <div style="font-size:12px;color:#606266;margin-top:4px">
                  上次接种：{{ fmtDate(s.last_vacc_date) }} ｜
                  下次到期：{{ fmtDate(s.next_due_date) }}
                </div>
              </template>
            </el-alert>
          </el-col>
        </el-row>
      </el-card>

      <el-row :gutter="16">
        <!-- 接种时间线 -->
        <el-col :span="14">
          <el-card class="card-shadow" header="完整接种史">
            <el-timeline v-if="pet.vaccinations?.length">
              <el-timeline-item
                v-for="v in pet.vaccinations"
                :key="v.id"
                :timestamp="`${v.vacc_date} · ${v.doctor || ''}`"
                placement="top"
                :type="v.reaction_level === 'severe' ? 'danger'
                        : v.reaction_level === 'mild' ? 'warning' : 'success'">
                <el-card shadow="hover" style="padding:4px 8px">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <strong>{{ v.vaccine_name }}</strong>
                    <el-tag size="small" :type="v.reaction_level === 'none' ? 'success'
                            : v.reaction_level === 'severe' ? 'danger' : 'warning'">
                      {{ v.reaction_level === 'none' ? '无不良反应'
                         : v.reaction_level === 'severe' ? '严重不良反应' : '轻微不良反应' }}
                    </el-tag>
                  </div>
                  <div style="font-size:13px;color:#606266;margin-top:6px;line-height:1.8">
                    批号：{{ v.batch_no || '—' }}　厂家：{{ v.manufacturer || '—' }}<br />
                    注射部位：{{ v.site || '—' }}
                    下次建议：<el-text tag="b" type="primary">{{ fmtDate(v.next_due_date) }}</el-text>
                  </div>
                  <el-text v-if="v.adverse_reaction && v.adverse_reaction !== '无'"
                           type="danger" size="small">⚠ {{ v.adverse_reaction }}</el-text>
                </el-card>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无接种记录" :image-size="80" />
          </el-card>
        </el-col>

        <!-- 抗体检测 -->
        <el-col :span="10">
          <el-card class="card-shadow" header="抗体检测记录">
            <el-table :data="pet.antibodies" size="small" v-if="pet.antibodies?.length">
              <el-table-column prop="test_date" label="日期" width="105" />
              <el-table-column prop="vaccine_name" label="疫苗" min-width="110" />
              <el-table-column label="结果" width="80">
                <template #default="{ row }">
                  <el-tag size="small"
                    :style="{ color: RESULT_COLOR[row.result], borderColor: RESULT_COLOR[row.result] }"
                    effect="plain">{{ row.result }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="titer" label="滴度" width="70" />
            </el-table>
            <el-empty v-else description="暂无抗体检测" :image-size="80" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 随访计划历史 -->
      <el-card class="card-shadow" style="margin-top:16px" header="随访计划">
        <el-table :data="pet.followup_plans" size="small"
                  v-if="pet.followup_plans?.length">
          <el-table-column prop="plan_date" label="计划日期" width="110" />
          <el-table-column prop="vaccine_name" label="疫苗" min-width="130" />
          <el-table-column prop="assignee" label="负责人" width="90" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small"
                :type="(FOLLOWUP_STATUS_META[row.status].type as any)">
                {{ FOLLOWUP_STATUS_META[row.status].label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="160">
            <template #default="{ row }">{{ row.note || '—' }}</template>
          </el-table-column>
          <el-table-column label="最近更新" width="160">
            <template #default="{ row }">{{ row.updated_at || row.created_at }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无随访计划" :image-size="80" />
      </el-card>
    </template>
  </div>
</template>
