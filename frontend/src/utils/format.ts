import dayjs from 'dayjs'

export const fmtDate = (d?: string | null) =>
  d ? dayjs(d).format('YYYY-MM-DD') : '—'

export const STATUS_META: Record<string, { label: string; type: string; color: string }> = {
  overdue:   { label: '已逾期', type: 'danger',  color: '#f56c6c' },
  due_soon:  { label: '即将到期', type: 'warning', color: '#e6a23c' },
  valid:     { label: '免疫有效', type: 'success', color: '#67c23a' },
  none:      { label: '从未接种', type: 'info',    color: '#909399' },
  too_young: { label: '未到日龄', type: 'info',    color: '#c0c4cc' },
}

export const FOLLOWUP_STATUS_META: Record<string, { label: string; type: string; color: string }> = {
  pending:   { label: '待确认', type: 'warning', color: '#e6a23c' },
  confirmed: { label: '已确认', type: 'primary', color: '#409eff' },
  completed: { label: '已完成', type: 'success', color: '#67c23a' },
  cancelled: { label: '已取消', type: 'info',    color: '#909399' },
}

export const RESULT_COLOR: Record<string, string> = {
  '阳性': '#67c23a',
  '弱阳性': '#e6a23c',
  '阴性': '#f56c6c',
}

export const SPECIES_EMOJI: Record<string, string> = {
  '犬': '🐕',
  '猫': '🐈',
  '兔': '🐇',
}

// 库存批次实时状态（按剩余数量与有效期计算）
export const BATCH_STATUS_META: Record<string, { label: string; color: string }> = {
  normal:   { label: '正常', color: '#67c23a' },
  low:      { label: '低库存', color: '#409eff' },
  expiring: { label: '临期', color: '#e6a23c' },
  expired:  { label: '已过期', color: '#f56c6c' },
}

export const STOCK_TXN_META: Record<string, { label: string; type: string }> = {
  inbound: { label: '入库', type: 'success' },
  consume: { label: '消耗', type: 'danger' },
  adjust:  { label: '调整', type: 'warning' },
}

export function daysText(days: number | null): string {
  if (days === null || days === undefined) return '—'
  if (days < 0) return `逾期 ${-days} 天`
  if (days === 0) return '今日到期'
  return `剩余 ${days} 天`
}
