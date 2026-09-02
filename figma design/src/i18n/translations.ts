export const translations = {
  en: { loading: 'Loading…', back: 'BACK', systemOperational: 'SYSTEM OPERATIONAL', threatLevel: 'THREAT LEVEL: ELEVATED', language: 'Language', english: 'English', hindi: 'Hindi' },
  hi: { loading: 'लोड हो रहा है…', back: 'वापस', systemOperational: 'सिस्टम चालू है', threatLevel: 'खतरे का स्तर: ऊंचा', language: 'भाषा', english: 'अंग्रेज़ी', hindi: 'हिन्दी' },
} as const
export type Locale = keyof typeof translations
