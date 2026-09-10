import { lazy, type ComponentType } from 'react'
import { isModuleLoadError } from './moduleLoadError'

export function lazyRetry<T extends { default: ComponentType<any> }>(loader: () => Promise<T>) {
  return lazy(async () => {
    for (let attempt = 0; ; attempt++) {
      try {
        return await loader()
      } catch (error) {
        if (!isModuleLoadError(error) || attempt >= 2) throw error
        await new Promise(resolve => setTimeout(resolve, attempt === 0 ? 300 : 900))
      }
    }
  })
}
