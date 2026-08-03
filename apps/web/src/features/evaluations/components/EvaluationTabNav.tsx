import { NavLink } from 'react-router-dom'

const TABS = [
  { suffix: '', label: 'Resumen' },
  { suffix: '/requirements', label: 'Requerimientos' },
  { suffix: '/vendors', label: 'Proveedores' },
  { suffix: '/assignments', label: 'Asignaciones' },
  { suffix: '/approval', label: 'Aprobación' },
  { suffix: '/proposals', label: 'Propuestas' },
  { suffix: '/qna', label: 'Q&A' },
  { suffix: '/results', label: 'Resultados' },
]

export function EvaluationTabNav({ evaluationId }: { evaluationId: string }) {
  return (
    <nav aria-label="Secciones de la evaluación" className="mt-4 flex gap-4 border-b border-border">
      {TABS.map((tab) => (
        <NavLink
          key={tab.suffix}
          to={`/evaluations/${evaluationId}${tab.suffix}`}
          end={tab.suffix === ''}
          className={({ isActive }) =>
            `border-b-2 pb-2 text-sm ${
              isActive
                ? 'border-foreground font-medium text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
