import type { QuantFilterFieldKey } from '../types/quant'

export const BEAR_SWING_FIELDS: { key: QuantFilterFieldKey; label: string; unit: string }[] = [
  { key: 'bear-bank-tightness', label: '银行流动性紧张度（22:30已知）', unit: '分' },
  { key: 'bear-position60-pct', label: '60D价格位置历史分位', unit: '%' },
  { key: 'bear-return-1d', label: '指数1D涨跌幅', unit: '%' },
  { key: 'bear-mo-vix-pct', label: 'MO隐含波动率历史分位', unit: '%' },
  { key: 'bear-citic14-pct', label: '中信IM净空14D增量历史分位', unit: '%' },
]
