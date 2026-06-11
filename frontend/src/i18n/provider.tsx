import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { interpolate, normalizeLanguage, resolveMessage } from "@/i18n";
import type { TranslationKey } from "@/i18n";
import type { LanguageCode } from "@/types/music";

interface I18nContextValue {
  language: LanguageCode;
  setLanguage: (language: LanguageCode) => void;
  t: (key: TranslationKey, values?: Record<string, string | number>) => string;
}

export const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({
  children,
  initialLanguage = "en",
}: PropsWithChildren<{ initialLanguage?: LanguageCode }>) {
  const [language, setLanguageState] = useState<LanguageCode>(normalizeLanguage(initialLanguage));

  useEffect(() => {
    setLanguageState(normalizeLanguage(initialLanguage));
  }, [initialLanguage]);

  const setLanguage = useCallback((nextLanguage: LanguageCode) => {
    setLanguageState(normalizeLanguage(nextLanguage));
  }, []);

  const t = useCallback((key: TranslationKey, values?: Record<string, string | number>) => {
    return interpolate(resolveMessage(language, key), values);
  }, [language]);

  const value = useMemo(() => ({
    language,
    setLanguage,
    t,
  }), [language, setLanguage, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
