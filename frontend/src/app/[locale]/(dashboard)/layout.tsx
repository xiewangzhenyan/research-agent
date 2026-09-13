import { ProjectProvider } from "@/components/projects/project-provider";
import { Header, Sidebar } from "@/components/layout";
import { AuthGuard } from "@/components/layout/auth-guard";
import { CommandPalette } from "@/components/layout/command-palette";
import { MobileTabBar } from "@/components/layout/mobile-tab-bar";
import { PageTransition } from "@/components/layout/page-transition";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ProjectProvider>
        <div className="cosmic-workspace console-shell">
          <Header />
          <Sidebar />
          <main id="main" tabIndex={-1} className="console-main">
            <PageTransition>{children}</PageTransition>
          </main>
          <MobileTabBar />
          <CommandPalette />
        </div>
      </ProjectProvider>
    </AuthGuard>
  );
}
