import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * Renders a page component wrapped in the same providers `main.tsx` sets
 * up (TanStack Query + React Router), so pages that call `useQuery`,
 * `useParams`, or `useNavigate` work the same way they do in the app.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", path = "/" }: { route?: string; path?: string } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
