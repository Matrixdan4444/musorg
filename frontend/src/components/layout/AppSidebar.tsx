import { motion } from "framer-motion";
import {
  FolderCog,
  HeartPulse,
  PencilLine,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/i18n/useI18n";
import { useAppMotion } from "@/lib/motion";
import { BrandLogo } from "@/components/layout/BrandLogo";
import type { AppPage, SidebarNavItem } from "@/types/layout";

const icons = {
  import: HeartPulse,
  "batch-edit": PencilLine,
  settings: FolderCog,
} as const;

interface AppSidebarProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  statusLabel: string;
}

export function AppSidebar({ activePage, onNavigate, statusLabel }: AppSidebarProps) {
  const { t } = useI18n();
  const appMotion = useAppMotion();
  const navItems: SidebarNavItem[] = [
    { id: "import", label: t("sidebar.import") },
    { id: "batch-edit", label: t("sidebar.batch") },
    { id: "settings", label: t("sidebar.settings") },
  ];

  return (
    <aside className="glass-panel glass-edge hidden min-h-screen flex-col rounded-none border-b-0 border-l-0 border-t-0 bg-[linear-gradient(180deg,_hsl(var(--panel)/0.86),_hsl(var(--panel)/0.72))] px-5 py-6 lg:flex">
      <div className="flex items-center gap-3 px-1">
        <BrandLogo className="h-10 w-10" />
        <p className="font-brand text-[18px] font-bold tracking-tight text-[hsl(var(--text-strong))]">
          Musorg
        </p>
      </div>

      <nav className="mt-8 flex flex-1 flex-col gap-1.5">
        {navItems.map((item, index) => {
          const Icon = icons[item.id];
          const active = item.id === activePage;

          return (
            <motion.button
              key={item.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2, delay: index * 0.04 }}
              whileTap={appMotion.tap}
              className={cn(
                "group relative z-[1] flex items-center gap-3 overflow-hidden rounded-2xl border px-3 py-2.5 text-left transition-[border-color,background-color,color,transform]",
                active
                  ? "border-[hsl(var(--accent)/0.24)] bg-[linear-gradient(135deg,_hsl(var(--accent)/0.17),_hsl(var(--surface-selected))_42%,_transparent_150%)] text-[hsl(var(--text-strong))] shadow-[inset_0_1px_0_hsl(var(--border-strong)/0.24)]"
                  : "border-transparent text-muted-foreground hover:border-border-soft/70 hover:bg-surface-subtle/70 hover:text-[hsl(var(--text-base))]",
              )}
              type="button"
              onClick={() => onNavigate(item.id)}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border transition-colors",
                  active
                    ? "border-[hsl(var(--accent)/0.22)] bg-[hsl(var(--accent)/0.14)] text-[hsl(var(--brand-fg))]"
                    : "border-transparent bg-surface-subtle/45 text-muted-foreground group-hover:border-border-soft/75 group-hover:bg-surface-subtle/90 group-hover:text-[hsl(var(--text-base))]",
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1 text-[14px] font-medium">{item.label}</span>
              {item.helper ? (
                <span className="rounded-full bg-[hsl(var(--danger-border))] px-2 py-0.5 text-[10px] text-white">
                  {item.helper}
                </span>
              ) : null}
            </motion.button>
          );
        })}
      </nav>

      <div className="space-y-3 pt-4">
        <div className="relative overflow-hidden rounded-2xl border border-border-soft/75 bg-[linear-gradient(135deg,_hsl(var(--accent)/0.12),_hsl(var(--surface-subtle))_42%,_hsl(var(--surface-subtle))/0.94)] px-4 py-3 text-[13px] text-[hsl(var(--text-base))]">
          {statusLabel}
        </div>
      </div>
    </aside>
  );
}
