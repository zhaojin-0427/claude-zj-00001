import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/reminders' },
  {
    path: '/pets',
    name: 'pets',
    component: () => import('../views/PetsView.vue'),
    meta: { title: '宠物档案', icon: 'Coin' },
  },
  {
    path: '/pets/:id',
    name: 'pet-detail',
    component: () => import('../views/PetDetailView.vue'),
    meta: { title: '宠物详情', hidden: true },
  },
  {
    path: '/vaccinate',
    name: 'vaccinate',
    component: () => import('../views/VaccinateView.vue'),
    meta: { title: '接种登记', icon: 'Syringe' },
  },
  {
    path: '/inventory',
    name: 'inventory',
    component: () => import('../views/InventoryView.vue'),
    meta: { title: '疫苗库存', icon: 'Box' },
  },
  {
    path: '/reminders',
    name: 'reminders',
    component: () => import('../views/RemindersView.vue'),
    meta: { title: '到期提醒', icon: 'Bell' },
  },
  {
    path: '/followups',
    name: 'followups',
    component: () => import('../views/FollowupsView.vue'),
    meta: { title: '随访计划', icon: 'Calendar' },
  },
  {
    path: '/antibody',
    name: 'antibody',
    component: () => import('../views/AntibodyView.vue'),
    meta: { title: '抗体趋势', icon: 'TrendCharts' },
  },
  {
    path: '/stats',
    name: 'stats',
    component: () => import('../views/StatsView.vue'),
    meta: { title: '数据统计', icon: 'DataAnalysis' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
