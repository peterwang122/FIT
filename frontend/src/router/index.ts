import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ProgressView from '../views/ProgressView.vue'
import QuantView from '../views/QuantView.vue'
import StocksView from '../views/StocksView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/stocks', component: StocksView },
    { path: '/quant', component: QuantView },
    { path: '/progress', component: ProgressView },
  ],
})
