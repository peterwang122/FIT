<script setup lang="ts">
import type { StockCandle } from '../types/stock'

defineProps<{ candles: StockCandle[] }>()
</script>

<template>
  <div class="card">
    <h3>日线数据预览（后续替换为专业K线图）</h3>
    <table>
      <thead>
        <tr>
          <th>交易日</th>
          <th>开盘</th>
          <th>最高</th>
          <th>最低</th>
          <th>收盘</th>
          <th>涨跌幅%</th>
          <th>成交量</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in candles.slice(-20)" :key="row.trade_date">
          <td>{{ row.trade_date }}</td>
          <td>{{ row.open }}</td>
          <td>{{ row.high }}</td>
          <td>{{ row.low }}</td>
          <td>{{ row.close }}</td>
          <td>{{ row.pct_chg }}</td>
          <td>{{ row.vol }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  border-bottom: 1px solid #e5e7eb;
  padding: 8px;
  font-size: 13px;
}
</style>
