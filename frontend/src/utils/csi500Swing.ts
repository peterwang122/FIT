import type { QuantFilterFieldKey } from '../types/quant'
import fields from './csi500SwingFields.json'

export const CSI500_SWING_FIELDS = fields.map((field) => ({
  ...field, key: field.key as QuantFilterFieldKey,
}))
export const CSI500_SWING_PLOT_FIELDS = CSI500_SWING_FIELDS.filter((field) => field.plot)
