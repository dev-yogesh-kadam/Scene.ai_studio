// The studio: the providers every page needs, and the router.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createBrowserRouter } from 'react-router';
import { OverlayHost } from '../common/components/OverlayHost';
import { oldAddress } from '../common/LinkClicks';
import { routes } from './routes';

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // The studio's data changes when the user acts or the live connection says so, not on a timer or window focus.
      queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 30_000 },
    },
  });
}

export function createRouter() {
  oldAddress();
  return createBrowserRouter(routes);
}

export function App({ client, router }: { client: QueryClient; router: ReturnType<typeof createBrowserRouter> }) {
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <OverlayHost />
    </QueryClientProvider>
  );
}
