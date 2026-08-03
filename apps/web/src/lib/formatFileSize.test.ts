import { describe, expect, it } from 'vitest'
import { formatFileSize } from '@/lib/formatFileSize'

describe('formatFileSize', () => {
  it('renders bytes below 1024 without conversion', () => {
    expect(formatFileSize(512)).toBe('512 B')
  })

  it('converts to KB/MB with one decimal', () => {
    expect(formatFileSize(2048)).toBe('2.0 KB')
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('caps at GB for very large values', () => {
    expect(formatFileSize(2 * 1024 * 1024 * 1024)).toBe('2.0 GB')
  })
})
