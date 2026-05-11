import type { ReactNode } from "react";
import { NavSidebar } from "./NavSidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen grid grid-cols-[220px_1fr] bg-bny-paper text-bny-ink">
      <NavSidebar />
      <main className="px-8 py-6 max-w-[1200px] w-full">
        {children}
      </main>
    </div>
  );
}
