import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/companies", label: "Companies" },
  { to: "/jobs", label: "Jobs" },
  { to: "/import", label: "Import" },
] as const;

/** App shell: top nav + routed page content. Desktop-first, min-width layout. */
export function Layout() {
  return (
    <div className="min-h-screen min-w-[1024px]">
      <header className="border-border bg-background sticky top-0 z-10 border-b">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-8 py-4">
          <span className="text-sm font-semibold tracking-tight">Lead Intelligence</span>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
