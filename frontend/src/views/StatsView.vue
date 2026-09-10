<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { statsApi } from '../api'
import type { Stats } from '../api/types'
import { BarChart, DoughnutChart } from '../components/Charts'

const stats = ref<Stats | null>(null)
const loading = ref(true)

const metricCards = computed(() => {
  if (!stats.value) return []
  const s = stats.value
  return [
    { label: '综合疫苗接种覆盖率', value: s.overall_coverage_rate, suffix: '%',
      sub: `有效免疫 ${s.overdue.applicable - s.overdue.unvaccinated} / 应种 ${s.overdue.applicable} 组合`,
      color: '#409eff', icon: '💉' },
    { label: '不良反应率', value: s.adverse.rate, suffix: '%',
      sub: `${s.vaccination_count} 针次中：轻微 ${s.adverse.mild} · 严重 ${s.adverse.severe}`,
      color: '#e6a23c', icon: '⚠️' },
    { label: '到期未接种比例', value: s.overdue.rate, suffix: '%',
      sub: `逾期 ${s.overdue.overdue} · 从未接种 ${s.overdue.never}`,
      color: '#f56c6c', icon: '⏰' },
    { label: '抗体阳性率', value: s.antibody.positive_rate, suffix: '%',
      sub: `共 ${s.antibody.total} 次检测`,
      color: '#67c23a', icon: '🛡️' },
  ]
})

// 随访计划指标
const followupCards = computed(() => {
  if (!stats.value) return []
  const f = stats.value.followup
  return [
    { label: '随访计划总数', value: f.total, suffix: ' 条',
      sub: `待确认 ${f.pending} · 已确认 ${f.confirmed} · 已取消 ${f.cancelled}`,
      color: '#409eff', icon: '📋' },
    { label: '七日内待执行', value: f.due_in_7_days, suffix: ' 条',
      sub: '未来 7 天内到期的未结束计划',
      color: '#e6a23c', icon: '⏳' },
    { label: '随访计划完成率', value: f.completion_rate, suffix: '%',
      sub: `已完成 ${f.completed} / ${f.total} 条`,
      color: '#67c23a', icon: '✅' },
  ]
})

// 疫苗库存指标
const inventoryCards = computed(() => {
  if (!stats.value) return []
  const inv = stats.value.inventory
  return [
    { label: '当前库存总量', value: inv.stock_total, suffix: ' 支',
      sub: `未过期可用 ${inv.stock_valid} 支 · 共 ${inv.batch_count} 个批次`,
      color: '#409eff', icon: '📦' },
    { label: '30 天内临期数量', value: inv.expiring_soon_qty, suffix: ' 支',
      sub: `涉及 ${inv.expiring_soon_batches} 个临期批次`,
      color: '#e6a23c', icon: '⏰' },
    { label: '低库存批次数', value: inv.low_batch_count, suffix: ' 个',
      sub: `剩余数量 ≤ 预警阈值${inv.expired_batch_count ? ` · 已过期 ${inv.expired_batch_count} 批` : ''}`,
      color: '#f56c6c', icon: '⚠️' },
    { label: '本月消耗量', value: inv.month_consumed, suffix: ' 支',
      sub: `本月接种消耗 ${inv.month_consume_times} 次`,
      color: '#67c23a', icon: '💉' },
  ]
})

// 随访计划状态构成
const followupData = computed(() => ({
  labels: ['待确认', '已确认', '已完成', '已取消'],
  datasets: [{
    data: stats.value
      ? [stats.value.followup.pending, stats.value.followup.confirmed,
         stats.value.followup.completed, stats.value.followup.cancelled]
      : [],
    backgroundColor: ['#e6a23c', '#409eff', '#67c23a', '#909399'],
  }],
}))

// 各疫苗覆盖率
const coverageData = computed(() => ({
  labels: stats.value?.coverage.map(c => c.vaccine_name) || [],
  datasets: [
    {
      label: '有效免疫率 %',
      data: stats.value?.coverage.map(c => c.coverage_rate) || [],
      backgroundColor: '#409eff',
    },
    {
      label: '曾接种率 %',
      data: stats.value?.coverage.map(c => c.ever_rate) || [],
      backgroundColor: '#a0cfff',
    },
  ],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y' as const,
  scales: { x: { max: 100, ticks: { callback: (v: any) => v + '%' } } },
  plugins: { legend: { position: 'bottom' as const } },
}

// 不良反应
const adverseData = computed(() => ({
  labels: ['无不良反应', '轻微', '严重'],
  datasets: [{
    data: stats.value
      ? [stats.value.adverse.total - stats.value.adverse.reaction_count,
         stats.value.adverse.mild, stats.value.adverse.severe]
      : [],
    backgroundColor: ['#67c23a', '#e6a23c', '#f56c6c'],
  }],
}))

// 到期未接种构成
const overdueData = computed(() => ({
  labels: ['免疫有效', '已逾期', '从未接种'],
  datasets: [{
    data: stats.value
      ? [stats.value.overdue.applicable - stats.value.overdue.unvaccinated,
         stats.value.overdue.overdue, stats.value.overdue.never]
      : [],
    backgroundColor: ['#67c23a', '#f56c6c', '#909399'],
  }],
}))

// 抗体结果构成
const antibodyData = computed(() => ({
  labels: ['阳性', '弱阳性', '阴性'],
  datasets: [{
    data: stats.value
      ? [stats.value.antibody.positive, stats.value.antibody.weak,
         stats.value.antibody.negative]
      : [],
    backgroundColor: ['#67c23a', '#e6a23c', '#f56c6c'],
  }],
}))

// 分疫苗阳性率
const abByVacData = computed(() => ({
  labels: stats.value?.antibody.items.map(i => i.vaccine_name) || [],
  datasets: [{
    label: '阳性率 %',
    data: stats.value?.antibody.items.map(i => i.positive_rate) || [],
    backgroundColor: stats.value?.antibody.items.map(i =>
      i.positive_rate >= 70 ? '#67c23a' : i.positive_rate >= 40 ? '#e6a23c' : '#f56c6c'),
  }],
}))

const abBarOptions = {
  responsive: true,
  maintainAspectRatio: false,
  scales: { y: { max: 100, ticks: { callback: (v: any) => v + '%' } } },
  plugins: { legend: { display: false } },
}

// 月度接种趋势
const monthlyData = computed(() => ({
  labels: stats.value?.monthly.map(m => m.month) || [],
  datasets: [{
    label: '接种针次',
    data: stats.value?.monthly.map(m => m.cnt) || [],
    borderColor: '#409eff',
    backgroundColor: '#409eff22',
    fill: true,
    tension: 0.35,
  }],
}))

const donutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'bottom' as const } },
}

onMounted(async () => {
  try {
    stats.value = await statsApi.get()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading">
    <!-- 四项核心指标 -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col v-for="m in metricCards" :key="m.label" :span="6">
        <div class="stat-card">
          <div class="icon-box" :style="{ background: m.color }">{{ m.icon }}</div>
          <div>
            <div class="stat-value">{{ m.value }}<span style="font-size:15px">{{ m.suffix }}</span></div>
            <div class="stat-label">{{ m.label }}</div>
            <div class="stat-sub">{{ m.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 疫苗库存指标 -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col v-for="m in inventoryCards" :key="m.label" :span="6">
        <div class="stat-card">
          <div class="icon-box" :style="{ background: m.color }">{{ m.icon }}</div>
          <div>
            <div class="stat-value">{{ m.value }}<span style="font-size:15px">{{ m.suffix }}</span></div>
            <div class="stat-label">{{ m.label }}</div>
            <div class="stat-sub">{{ m.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 随访计划指标 -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col v-for="m in followupCards" :key="m.label" :span="8">
        <div class="stat-card">
          <div class="icon-box" :style="{ background: m.color }">{{ m.icon }}</div>
          <div>
            <div class="stat-value">{{ m.value }}<span style="font-size:15px">{{ m.suffix }}</span></div>
            <div class="stat-label">{{ m.label }}</div>
            <div class="stat-sub">{{ m.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:16px">
      <!-- 覆盖率 -->
      <el-col :span="14">
        <el-card class="card-shadow" header="各疫苗接种覆盖率">
          <div style="height:340px">
            <BarChart :chart-data="coverageData" :options="chartOptions" />
          </div>
        </el-card>
      </el-col>
      <!-- 覆盖率明细 -->
      <el-col :span="10">
        <el-card class="card-shadow" header="覆盖率明细">
          <el-table :data="stats?.coverage" size="small" max-height="340">
            <el-table-column prop="vaccine_name" label="疫苗" min-width="110" />
            <el-table-column prop="applicable" label="应种" width="55" align="center" />
            <el-table-column prop="valid" label="有效" width="55" align="center" />
            <el-table-column label="覆盖率" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small"
                  :type="row.coverage_rate >= 70 ? 'success'
                    : row.coverage_rate >= 40 ? 'warning' : 'danger'">
                  {{ row.coverage_rate }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6">
        <el-card class="card-shadow"
          :header="`不良反应构成（总 ${stats?.adverse.total ?? 0} 针次）`">
          <div style="height:250px">
            <DoughnutChart :chart-data="adverseData" :options="donutOptions" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="card-shadow"
          :header="`到期未接种构成（${stats?.overdue.rate ?? 0}%）`">
          <div style="height:250px">
            <DoughnutChart :chart-data="overdueData" :options="donutOptions" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="card-shadow"
          :header="`抗体检测结果构成（${stats?.antibody.total ?? 0} 次）`">
          <div style="height:250px">
            <DoughnutChart :chart-data="antibodyData" :options="donutOptions" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="card-shadow"
          :header="`随访计划状态构成（总 ${stats?.followup.total ?? 0} 条）`">
          <div style="height:250px">
            <DoughnutChart :chart-data="followupData" :options="donutOptions" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="12">
        <el-card class="card-shadow" header="近12月接种趋势">
          <div style="height:260px">
            <BarChart :chart-data="monthlyData"
                      :options="{ responsive: true, maintainAspectRatio: false,
                                  plugins: { legend: { display: false } } }" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="card-shadow" header="各疫苗抗体阳性率">
          <div style="height:260px">
            <BarChart :chart-data="abByVacData" :options="abBarOptions" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="card-shadow" header="近期不良反应记录">
      <el-table :data="stats?.recent_reactions" size="small" stripe>
        <el-table-column prop="vacc_date" label="接种日期" width="110" />
        <el-table-column prop="pet_name" label="宠物" width="90" />
        <el-table-column prop="vaccine_name" label="疫苗" min-width="120" />
        <el-table-column prop="adverse_reaction" label="不良反应情况" min-width="260">
          <template #default="{ row }">
            <el-text :type="row.adverse_reaction.startsWith('严重') ? 'danger' : 'warning'">
              {{ row.adverse_reaction }}
            </el-text>
          </template>
        </el-table-column>
        <el-table-column prop="doctor" label="处理医生" width="90" />
      </el-table>
    </el-card>
  </div>
</template>
