import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ProgressView from '../views/ProgressView.vue'
import QuantIndexView from '../views/QuantIndexView.vue'
import QuantStockView from '../views/QuantStockView.vue'
import QuantStrategiesView from '../views/QuantStrategiesView.vue'
import QuantView from '../views/QuantView.vue'
import StocksView from '../views/StocksView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/stocks', component: StocksView },
    {
      path: '/quant',
      component: QuantView,
      children: [
        { path: '', redirect: '/quant/index' },
        { path: 'index', component: QuantIndexView },
        { path: 'stock', component: QuantStockView },
        { path: 'strategies', component: QuantStrategiesView },
      ],
    },
    { path: '/progress', component: ProgressView },
  ],
})
