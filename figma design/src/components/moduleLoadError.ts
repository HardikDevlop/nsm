export function isModuleLoadError(error: unknown): boolean {
  return error instanceof Error && /error loading dynamically imported module|failed to fetch dynamically imported module|importing a module script failed|loading chunk .* failed/i.test(error.message)
}
