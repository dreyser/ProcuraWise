const UNITS = ['B', 'KB', 'MB', 'GB'] as const

/** Human-readable file size (Fase 16, documents) - binary (1024) units,
 * matching how `Settings.documents_max_file_size_mb` is computed on the
 * backend. Shared by every place that renders a Document's `size_bytes`
 * (vendor upload panel, requirement evidence widget, buyer read-only view). */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < UNITS.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${UNITS[unitIndex]}`
}
