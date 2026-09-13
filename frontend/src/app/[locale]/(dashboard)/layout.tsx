import { ProjectProvider, ProjectContent } from "@/components/projects/project-provider";
import { Header, Sidebar } from "@/components/layout";
import { AuthGuard } from "@/components/layout/auth-guard";
import { CommandPalette } from "@/components/layout/command-palette";
import { MobileTabBar } from "@/components/layout/mobile-tab-bar";
import { PageTransition } from "@/components/layout/page-transition";
import { GenerationConfigWarmup } from "@/hooks/use-generation-config";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <GenerationConfigWarmup />
      <ProjectProvider>
        <div className="cosmic-workspace console-shell">
          <Header />
          <Sidebar />
          <main id="main" tabIndex={-1} className="console-main">
            <ProjectContent>
              <PageTransition>{children}</PageTransition>
            </ProjectContent>
          </main>
          <MobileTabBar />
          <CommandPalette />
        </div>
      </ProjectProvider>
    </AuthGuard>
  );
}
