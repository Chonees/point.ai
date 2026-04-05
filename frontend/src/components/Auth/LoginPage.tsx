import { useState } from 'react'
import { isSupabaseConfigured } from '../../lib/supabase'

interface LoginPageProps {
  onSignIn: (email: string, password: string) => Promise<void>
  onSignUp: (email: string, password: string) => Promise<void>
  onGoogleSignIn: () => Promise<void>
  onSkip: () => void
}

export function LoginPage({ onSignIn, onSignUp, onGoogleSignIn, onSkip }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      if (mode === 'signin') {
        await onSignIn(email, password)
      } else {
        await onSignUp(email, password)
        setSuccess('Check your email to confirm your account')
      }
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Pointe<span className="text-white/30">.ai</span>
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Floor plan to professional DXF
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              required
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-colors focus:border-zinc-600"
            />
          </div>
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              minLength={6}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-colors focus:border-zinc-600"
            />
          </div>

          {error && (
            <p className="rounded-md bg-red-900/30 px-3 py-2 text-xs text-red-400">
              {error}
            </p>
          )}
          {success && (
            <p className="rounded-md bg-green-900/30 px-3 py-2 text-xs text-green-400">
              {success}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full cursor-pointer rounded-lg bg-white/[0.06] py-3 text-sm font-medium text-zinc-400 border border-zinc-800/60 transition-all hover:bg-white/[0.09] hover:text-zinc-300 disabled:opacity-50"
          >
            {loading ? '...' : mode === 'signin' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        {/* Google */}
        <button
          onClick={onGoogleSignIn}
          className="mt-3 w-full cursor-pointer rounded-lg border border-zinc-800/60 bg-white/[0.03] py-3 text-sm text-zinc-500 transition-all hover:bg-white/[0.06] hover:text-zinc-300"
        >
          Continue with Google
        </button>

        {/* Toggle mode */}
        <p className="mt-4 text-center text-xs text-zinc-600">
          {mode === 'signin' ? (
            <>
              No account?{' '}
              <button
                onClick={() => { setMode('signup'); setError('') }}
                className="cursor-pointer text-zinc-400 hover:text-zinc-300"
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <button
                onClick={() => { setMode('signin'); setError('') }}
                className="cursor-pointer text-zinc-400 hover:text-zinc-300"
              >
                Sign in
              </button>
            </>
          )}
        </p>

        {/* Skip (dev mode / no supabase) */}
        {!isSupabaseConfigured && (
          <button
            onClick={onSkip}
            className="mt-6 w-full cursor-pointer text-center text-xs text-zinc-700 hover:text-zinc-500"
          >
            Continue without account (dev mode)
          </button>
        )}
      </div>
    </div>
  )
}
