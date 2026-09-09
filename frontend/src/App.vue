<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const menuItems = computed(() =>
  router.getRoutes()
    .filter(r => !r.meta?.hidden && r.meta?.title)
    .map(r => ({
      path: r.path,
      title: r.meta!.title as string,
      icon: r.meta!.icon as string,
    })),
)

const activeIndex = computed(() => {
  if (route.path.startsWith('/pets')) return '/pets'
  return route.path
})
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-icon">🐾</span>
        <div class="logo-text">
          <strong>宠物疫苗档案</strong>
          <small>接种与到期提醒平台</small>
        </div>
      </div>
      <el-menu
        :default-active="activeIndex"
        router
        background-color="#001529"
        text-color="#b7c0cd"
        active-text-color="#fff"
      >
        <el-menu-item v-for="m in menuItems" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ route.meta?.title || '' }}</div>
        <div class="header-right">
          <el-tag type="success" effect="dark" round>演示环境</el-tag>
          <el-avatar :size="34">👨‍⚕️</el-avatar>
          <span class="doctor-name">王医生</span>
        </div>
      </el-header>
      <el-main>
        <!-- 不在 router-view 外包 <transition mode="out-in">：
             各页面为多根节点（fragment），Transition 要求单元素根节点，
             否则离场动画无法完成、新组件不会挂载，表现为导航后内容空白 -->
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.aside {
  background: #001529;
  overflow-y: auto;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  color: #fff;
}
.logo-icon { font-size: 30px; }
.logo-text { display: flex; flex-direction: column; line-height: 1.3; }
.logo-text small { color: #8c98a8; font-size: 11px; }
:deep(.el-menu) { border-right: none; }
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}
.header-title { font-size: 17px; font-weight: 600; color: #303133; }
.header-right { display: flex; align-items: center; gap: 10px; }
.doctor-name { color: #606266; font-size: 14px; }
</style>
