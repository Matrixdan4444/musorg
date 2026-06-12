import type { PropsWithChildren, ReactNode } from "react";

interface AppShellProps extends PropsWithChildren {
  header: ReactNode;
  sidebar: ReactNode;
}

export function AppShell({ children, header, sidebar }: AppShellProps) {
  return (
    <div className="app-shell-grid">
      {sidebar}
      <div className="flex min-h-screen min-w-0 flex-col">
        <div className="mx-auto flex min-h-screen w-full max-w-[var(--shell-max-width)] flex-1 flex-col">
          {header}
          <main className="app-page-content flex min-h-0 flex-1 flex-col px-3 py-3 md:px-4 md:py-4 lg:px-5 lg:py-5">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
