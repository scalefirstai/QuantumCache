import { jsx as _jsx } from "react/jsx-runtime";
import { render } from "@testing-library/react";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider, } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
export function renderWithRouter({ initialEntries, routes }) {
    const root = createRootRoute({ component: () => _jsx(Outlet, {}) });
    const children = routes.map((spec) => createRoute({
        getParentRoute: () => root,
        path: spec.path,
        component: spec.Component,
        ...(spec.validateSearch ? { validateSearch: spec.validateSearch } : {}),
    }));
    const tree = root.addChildren(children);
    const history = createMemoryHistory({ initialEntries });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const router = createRouter({ routeTree: tree, history });
    const client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    const ui = (_jsx(QueryClientProvider, { client: client, children: _jsx(RouterProvider, { router: router }) }));
    return Object.assign(render(ui), { router });
}
