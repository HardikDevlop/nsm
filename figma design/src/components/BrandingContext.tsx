import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getBranding, type BrandingRecord } from '../lib/api'

const DEFAULT_BRANDING: BrandingRecord = {
  application_name: 'NMS',
  logo_url: null,
  allowed_themes: ['light', 'dark'],
}

const BrandingContext = createContext<BrandingRecord>(DEFAULT_BRANDING)

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING)

  useEffect(() => {
    const controller = new AbortController()
    void getBranding(controller.signal).then(setBranding).catch(() => undefined)
    return () => controller.abort()
  }, [])

  useEffect(() => {
    document.title = branding.application_name
  }, [branding.application_name])

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>
}

export function useBranding() {
  return useContext(BrandingContext)
}
