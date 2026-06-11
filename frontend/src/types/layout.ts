export type AppPage = "import" | "batch-edit" | "settings";

export interface SidebarNavItem {
  id: AppPage;
  label: string;
  helper?: string;
}
