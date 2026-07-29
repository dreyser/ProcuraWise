import { ActorProvider } from '@/actor/ActorContext'
import { AppRouter } from '@/app/router'

function App() {
  return (
    <ActorProvider>
      <AppRouter />
    </ActorProvider>
  )
}

export default App
