import { useEffect, useState } from 'react'

type HealthStatus = 'checking' | 'ok' | 'error'

function App() {
  const [status, setStatus] = useState<HealthStatus>('checking')

  useEffect(() => {
    fetch('/health')
      .then((response) => setStatus(response.ok ? 'ok' : 'error'))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <main>
      <h1>ProcuraWise</h1>
      <p>SaaS B2B multi-tenant que convierte una necesidad de compra en un proceso RFP riguroso.</p>
      <p>API status: {status}</p>
    </main>
  )
}

export default App
