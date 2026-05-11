import { render } from "@testing-library/react";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

interface RouteSpec {
  path: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any;
  validateSearch?: (s: Record<string, unknown>) => Record<string, unknown>;
}

interface Options {
  initialEntries: string[];
  routes: RouteSpec[];
}

export function renderWithRouter({ initialEntries, routes }: Options) {
  const root = createRootRoute({ component: () => <Outlet /> });
  const children = routes.map((spec) =>
    createRoute({
      getParentRoute: () => root,
      path: spec.path,
      component: spec.Component,
      ...(spec.validateSearch ? { validateSearch: spec.validateSearch } : {}),
    }),
  );
  const tree = root.addChildren(children);

  const history = createMemoryHistory({ initialEntries });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const router = createRouter({ routeTree: tree, history }) as any;

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const ui: ReactElement = (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );

  return Object.assign(render(ui), { router });
}
