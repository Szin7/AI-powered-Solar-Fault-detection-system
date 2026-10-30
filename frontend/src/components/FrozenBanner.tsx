'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { Lock } from 'lucide-react'

export function FrozenBanner({ isFrozen, toggleFreeze }: { isFrozen: boolean; toggleFreeze: () => void }) {
  return (
    <AnimatePresence>
      {isFrozen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="mb-4 px-5 py-3 rounded-xl border border-blue-400/50 bg-blue-500/10 flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 text-blue-400" />
            <div>
              <p className="font-semibold text-blue-300">Display Frozen</p>
              <p className="text-xs text-blue-400/70">
                Live data continues flowing to backend — only the display is paused.
                Inspect the reading below, then click Resume to continue.
              </p>
            </div>
          </div>
          <motion.button
            onClick={toggleFreeze}
            className="px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-400/50 text-blue-300 text-sm font-semibold hover:bg-blue-500/30 transition-all"
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          >
            Resume Live
          </motion.button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
