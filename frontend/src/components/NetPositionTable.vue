<script setup lang="ts">
import type { NetPositionTable } from '../types/stock'

defineProps<{ table: NetPositionTable | null; loading?: boolean }>()

function formatHandCount(value: number): string {
  return value.toLocaleString('zh-CN')
}
</script>

<template>
  <section class="net-table-panel">
    <p v-if="loading" class="muted">净持仓表加载中...</p>
    <p v-else-if="!table" class="muted">当前没有可展示的净持仓数据。</p>

    <table v-else class="net-table">
      <thead>
        <tr>
          <th colspan="5" class="net-table-title">{{ table.title }}</th>
        </tr>
        <tr>
          <th>指数</th>
          <th>空单</th>
          <th>多单</th>
          <th>净多空</th>
          <th>机构操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in table.rows" :key="row.product_code">
          <td>{{ row.index_name }}</td>
          <td>{{ formatHandCount(row.short_position) }}</td>
          <td>{{ formatHandCount(row.long_position) }}</td>
          <td :class="row.net_position > 0 ? 'net-short' : row.net_position < 0 ? 'net-long' : 'net-flat'">
            {{ row.net_position_text }}
          </td>
          <td>{{ row.action }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.net-table-panel {
  min-width: 0;
  overflow: hidden;
  overflow-x: auto;
}

.net-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.net-table th,
.net-table td {
  border: 1px solid #d6d3d1;
  padding: 8px 6px;
  text-align: center;
  font-size: 12px;
}

.net-table thead th {
  background: #fef3c7;
  color: #7c2d12;
  font-weight: 700;
}

.net-table-title {
  background: #fff7ed !important;
  color: #9a3412 !important;
  font-size: 14px;
  letter-spacing: 0.02em;
}

.net-table tbody tr:nth-child(even) {
  background: #fafaf9;
}

.net-short {
  color: #c2410c;
  font-weight: 700;
}

.net-long {
  color: #0f766e;
  font-weight: 700;
}

.net-flat {
  color: #475569;
  font-weight: 700;
}

.muted {
  padding: 12px 0;
  color: #64748b;
  font-size: 13px;
}
</style>
