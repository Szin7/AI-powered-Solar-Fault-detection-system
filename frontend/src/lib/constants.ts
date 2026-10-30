// Display labels from the original dashboard.
export const FAULT_INFO: Record<string, { color: string, gradient: string, icon: string, description: string }> = {
  'Inverter_Fault': { color: '#f43f5e', gradient: 'from-rose-500 to-pink-500', icon: '!', description: 'AC delivery is below the expected inverter output' },
  'Normal': {
    color: '#22c55e',
    gradient: 'from-green-500 to-emerald-500',
    icon: '✅',
    description: 'System operating normally'
  },
  'Open_Circuit': {
    color: '#a855f7',
    gradient: 'from-purple-500 to-violet-500',
    icon: '🔌',
    description: 'Circuit connection broken'
  },
  'Partial_Shading': {
    color: '#f59e0b',
    gradient: 'from-amber-500 to-orange-500',
    icon: '🌤️',
    description: 'Shadows blocking sunlight'
  },
  'Short_Circuit': {
    color: '#ef4444',
    gradient: 'from-red-500 to-rose-500',
    icon: '⚡',
    description: 'Critical: Short circuit detected'
  },
  'Dust_Accumulation': {
    color: '#78716c',
    gradient: 'from-stone-500 to-stone-600',
    icon: '🌫️',
    description: 'Dust reducing panel efficiency'
  },
}

// Helper function to check if current reading is abnormal
export function isCurrentAbnormal(current: number): boolean {
  return current < 0 || current > 1.5
}
