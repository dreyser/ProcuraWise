import type { WizardStep } from './deriveWizardStep'

const STEP_LABELS: Record<WizardStep, string> = {
  1: 'Datos generales',
  2: 'Requerimientos',
  3: 'Proveedores',
  4: 'Revisión e inicio',
}

const STEPS: WizardStep[] = [1, 2, 3, 4]

interface WizardStepperProps {
  currentStep: WizardStep
  maxReachableStep: WizardStep
  onStepSelect: (step: WizardStep) => void
}

/** Steps beyond `maxReachableStep` (derived from the evaluation's real state,
 * see deriveWizardStep) are disabled - the stepper can never let a user jump
 * ahead of what the backend would actually accept. */
export function WizardStepper({ currentStep, maxReachableStep, onStepSelect }: WizardStepperProps) {
  return (
    <ol className="mt-4 flex gap-4 border-b border-border" aria-label="Pasos de la evaluación">
      {STEPS.map((step) => {
        const isActive = step === currentStep
        const isReachable = step <= maxReachableStep
        return (
          <li key={step}>
            <button
              type="button"
              disabled={!isReachable}
              onClick={() => onStepSelect(step)}
              aria-current={isActive ? 'step' : undefined}
              className={`border-b-2 pb-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                isActive
                  ? 'border-foreground font-medium text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {step}. {STEP_LABELS[step]}
            </button>
          </li>
        )
      })}
    </ol>
  )
}
