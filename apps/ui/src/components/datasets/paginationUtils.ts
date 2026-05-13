export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 25;

/**
 * Apply page+pageSize to an already-filtered array. Returns the slice
 * for the current page and total page count so the consumer can drive
 * `<Pagination>`.
 */
export function paginate<T>(items: T[], page: number, pageSize: number) {
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const start = safePage * pageSize;
  const end = Math.min(start + pageSize, total);
  return {
    pageItems: items.slice(start, end),
    pageCount,
    safePage,
    rangeStart: total === 0 ? 0 : start + 1,
    rangeEnd: end,
    total,
  };
}
