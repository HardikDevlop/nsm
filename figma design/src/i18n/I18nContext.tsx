import { createContext, useContext, useState, type ReactNode } from 'react'
import { translations, type Locale } from './translations'

type I18nValue = { locale: Locale; setLocale: (locale: Locale) => void; t: typeof translations.en }
const Context = createContext<I18nValue>({ locale: 'en', setLocale: () => {}, t: translations.en })

function readLocale(): Locale {
  if (typeof window === 'undefined') return 'en'
  const value = window.localStorage.getItem('nms.locale')
  return value === 'hi' ? 'hi' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readLocale)
  const setLocale = (value: Locale) => {
    setLocaleState(value)
    window.localStorage.setItem('nms.locale', value)
  }

  return <Context.Provider value={{ locale, setLocale, t: translations[locale] }}>{children}</Context.Provider>
}

export function useI18n() { return useContext(Context) }
