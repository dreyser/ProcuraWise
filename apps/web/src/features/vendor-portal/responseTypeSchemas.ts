import { z } from 'zod'

/** Mirrors the backend validator exactly (proposals/service.py:23,
 * validate_answer_value) - see plan §19. Client-side only prevents obvious
 * mistakes before a round trip; the backend remains authoritative. */
export const CURRENCY_CODES = ['MXN', 'USD'] as const

export const currencySchema = z.object({
  amount: z.coerce.number().min(0, 'El monto debe ser mayor o igual a 0'),
  currency_code: z.enum(CURRENCY_CODES),
})

export const percentageSchema = z.coerce
  .number()
  .min(0, 'Debe estar entre 0 y 100')
  .max(100, 'Debe estar entre 0 y 100')

export const numberSchema = z.coerce.number()

export const dateSchema = z
  .string()
  .refine((value) => !Number.isNaN(Date.parse(value)), 'Ingresa una fecha válida')

export const urlSchema = z
  .string()
  .refine(
    (value) => value.startsWith('http://') || value.startsWith('https://'),
    'La URL debe empezar con http:// o https://',
  )
