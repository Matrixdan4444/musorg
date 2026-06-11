import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getLibrarySettings } from "@/lib/api/music";
import { BatchEditingPage } from "@/pages/BatchEditingPage";
import { ImportAlbumsPage } from "@/pages/ImportAlbumsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { getRuntimeConfig } from "@/lib/runtime";
import { useI18n } from "@/i18n/useI18n";
import { useTheme } from "@/theme/useTheme";
import type { AppPage } from "@/types/layout";


function StartupScreen({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background text-foreground antialiased">
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="app-startup-panel w-full max-w-[420px] rounded-[28px] px-8 py-8 text-center">
          <div className="app-brand-glow mx-auto h-12 w-12 rounded-2xl" />
          <h1 className="mt-5 text-[18px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
            {title}
          </h1>
          <p className="mt-2 text-[13px] leading-6 text-muted-foreground">{detail}</p>
          {action ? <div className="mt-5">{action}</div> : null}
        </div>
      </div>
    </div>
  );
}

function PageSlot({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  const inertProps = active ? {} : { inert: true };

  return (
    <div
      aria-hidden={!active}
      className={active ? "app-page-slot-active" : "app-page-slot-inactive"}
      {...inertProps}
    >
      {children}
    </div>
  );
}

function AppContent() {
  const runtime = getRuntimeConfig();
  const { t, setLanguage } = useI18n();
  const { setAppearance } = useTheme();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [page, setPage] = useState<AppPage>("import");
  const [visitedPages, setVisitedPages] = useState<Record<AppPage, boolean>>({
    import: true,
    "batch-edit": false,
    settings: false,
  });

  function handleNavigate(nextPage: AppPage) {
    setVisitedPages((current) => (
      current[nextPage]
        ? current
        : { ...current, [nextPage]: true }
    ));
    setPage(nextPage);
  }

  useEffect(() => {
    let cancelled = false;

    async function waitForBackend() {
      setReady(false);
      setError(null);

      for (let retry = 0; retry < 20; retry += 1) {
        try {
          const [response, settings] = await Promise.all([
            fetch(`${runtime.apiBaseUrl}/health`, {
              headers: { Accept: "application/json" },
            }),
            getLibrarySettings(),
          ]);

          if (!response.ok) {
            throw new Error(`Backend returned ${response.status}.`);
          }

          if (!cancelled) {
            setLanguage(settings.language);
            setAppearance({
              themeMode: settings.themeMode,
              accentColor: settings.accentColor,
            });
            setReady(true);
          }
          return;
        } catch (err) {
          if (cancelled) {
            return;
          }

          if (retry === 19) {
            setError(err instanceof Error ? err.message : t("app.errors.backendUnavailable"));
            return;
          }

          await new Promise((resolve) => window.setTimeout(resolve, 250));
        }
      }
    }

    void waitForBackend();

    return () => {
      cancelled = true;
    };
  }, [attempt, runtime.apiBaseUrl, setAppearance, setLanguage, t]);

  if (!ready && !error) {
    return (
      <StartupScreen
        title={t("app.startup.title")}
        detail={runtime.mode === "dev" ? t("app.startup.detailDev") : t("app.startup.detailProd")}
      />
    );
  }

  if (error) {
    return (
      <StartupScreen
        title={t("app.unavailable.title")}
        detail={error}
        action={(
          <button
            className="app-button-primary inline-flex h-11 items-center justify-center rounded-2xl px-5 text-[13px] font-semibold transition"
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            {t("app.unavailable.retry")}
          </button>
        )}
      />
    );
  }

  return (
    <div className="app-page-stack bg-background text-foreground antialiased">
      <PageSlot active={page === "import"}>
        <ImportAlbumsPage activePage={page} onNavigate={handleNavigate} />
      </PageSlot>
      {visitedPages["batch-edit"] ? (
        <PageSlot active={page === "batch-edit"}>
          <BatchEditingPage activePage={page} onNavigate={handleNavigate} />
        </PageSlot>
      ) : null}
      {visitedPages.settings ? (
        <PageSlot active={page === "settings"}>
          <SettingsPage activePage={page} onNavigate={handleNavigate} />
        </PageSlot>
      ) : null}
    </div>
  );
}

export default function App() {
  return <AppContent />;
}
