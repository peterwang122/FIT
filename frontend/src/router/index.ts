import { createRouter, createWebHistory } from 'vue-router'

import AccountView from '../views/AccountView.vue'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import MarketsView from '../views/MarketsView.vue'
import ProgressView from '../views/ProgressView.vue'
import QuantIndexView from '../views/QuantIndexView.vue'
import QuantSequenceView from '../views/QuantSequenceView.vue'
import QuantStockView from '../views/QuantStockView.vue'
import QuantStrategiesView from '../views/QuantStrategiesView.vue'
import QuantView from '../views/QuantView.vue'
import StocksView from '../views/StocksView.vue'
import TasksManageView from '../views/TasksManageView.vue'
import TasksMonitorView from '../views/TasksMonitorView.vue'
import TasksStrategiesView from '../views/TasksStrategiesView.vue'
import TasksView from '../views/TasksView.vue'
import { useAuthStore } from '../stores/auth'
import { pinia } from '../stores'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/account', component: AccountView, meta: { requiresAuth: true } },
    { path: '/', component: HomeView, meta: { requiresAuth: true } },
    { path: '/stocks', component: StocksView, meta: { requiresAuth: true } },
    { path: '/markets', component: MarketsView, meta: { requiresAuth: true } },
    {
      path: '/quant',
      component: QuantView,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/quant/index' },
        { path: 'index', component: QuantIndexView },
        { path: 'stock', component: QuantStockView },
        { path: 'sequence', component: QuantSequenceView },
        { path: 'strategies', component: QuantStrategiesView },
      ],
    },
    {
      path: '/tasks',
      component: TasksView,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/tasks/manage' },
        { path: 'manage', component: TasksManageView },
        { path: 'strategies', component: TasksStrategiesView, meta: { requiresRoot: true } },
        { path: 'monitor', component: TasksMonitorView, meta: { requiresRoot: true } },
      ],
    },
    { path: '/progress', component: ProgressView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)
  await authStore.ensureInitialized()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return {
      path: '/login',
      query: to.fullPath && to.fullPath !== '/login' ? { redirect: to.fullPath } : undefined,
    }
  }

  if (to.meta.requiresRoot && !authStore.isRoot) {
    if (to.path.startsWith('/tasks')) {
      return '/tasks/manage'
    }
    return '/'
  }

  if (to.path === '/login' && authStore.isAuthenticated) {
    const redirect = typeof to.query.redirect === 'string' && to.query.redirect ? to.query.redirect : '/'
    return redirect
  }

  return true
})
