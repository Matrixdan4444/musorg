import { en } from "@/i18n/locales/en";
import { ru } from "@/i18n/locales/ru";
import type { LanguageCode } from "@/types/music";

export const locales = { en, ru } as const;

export type Messages = typeof en;

type Join<K, P> = K extends string ? P extends string ? `${K}.${P}` : never : never;
type NestedKeyOf<T> = T extends string ? never : {
  [K in keyof T & string]: T[K] extends string ? K : Join<K, NestedKeyOf<T[K]>>;
}[keyof T & string];

export type TranslationKey = NestedKeyOf<Messages>;

export function resolveMessage(language: LanguageCode, key: TranslationKey): string {
  const dictionary = locales[language];
  const value = key.split(".").reduce<unknown>((current, part) => {
    if (typeof current !== "object" || current === null || !(part in current)) {
      return null;
    }
    return (current as Record<string, unknown>)[part];
  }, dictionary);
  return typeof value === "string" ? value : key;
}

export function normalizeLanguage(language: string | null | undefined): LanguageCode {
  return language === "ru" ? "ru" : "en";
}

export function interpolate(message: string, values?: Record<string, string | number>) {
  if (!values) {
    return message;
  }
  return message.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}
