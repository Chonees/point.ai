import { memo } from 'react'
import { motion } from 'framer-motion'

export const Spinner = memo(function Spinner() {
  return (
    <motion.span
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
      className="inline-block w-3.5 h-3.5 border border-zinc-600 border-t-zinc-400 rounded-full"
    />
  )
})
