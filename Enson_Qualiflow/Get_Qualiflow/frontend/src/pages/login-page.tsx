import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { useAuth } from '../features/auth/auth-context'
import { login } from '../lib/api'

export function LoginPage() {
  const navigate = useNavigate()
  const { setToken, refetchMe } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const mutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: async (data) => {
      setToken(data.access_token)
      await refetchMe()
      navigate('/')
    },
  })

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <Card className="w-full max-w-md space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Login</h1>
          <p className="text-sm text-slate-400">Access saved analyses and run new extractions.</p>
        </div>
        <Input placeholder="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <Input
          placeholder="Password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {mutation.isError && <p className="text-sm text-rose-300">{mutation.error.message}</p>}
        <Button className="w-full" onClick={() => mutation.mutate()} disabled={!email || !password || mutation.isPending}>
          Sign In
        </Button>
        <p className="text-sm text-slate-400">
          No account?{' '}
          <Link className="text-sky-400 hover:text-sky-300" to="/register">
            Register
          </Link>
        </p>
      </Card>
    </div>
  )
}
