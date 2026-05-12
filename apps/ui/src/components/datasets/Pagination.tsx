import { useMemo } from "react";

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

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  testId = "pagination",
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: PageSize) => void;
  testId?: string;
}) {
  const { pageCount, safePage, rangeStart, rangeEnd } = useMemo(
    () => paginate(new Array(total).fill(0), page, pageSize),
    [page, pageSize, total],
  );

  if (total <= PAGE_SIZE_OPTIONS[0]) {
    // Nothing to paginate — but expose the size selector so it stays
    // present once filters narrow results back into range.
    return null;
  }

  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-3 mt-3 text-xs"
      data-testid={testId}
    >
      <div className="flex items-center gap-2 text-bny-slate">
        <label className="flex items-center gap-1.5">
          <span>Rows per page</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value) as PageSize)}
            className="px-1.5 py-1 rounded-md border border-bny-mist bg-white text-xs focus:outline-none focus:ring-2 focus:ring-bny-teal"
            data-testid={`${testId}-size`}
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <span data-testid={`${testId}-range`}>
          {rangeStart}–{rangeEnd} of {total}
        </span>
      </div>
      <div className="flex items-center gap-1">
        <PageButton
          onClick={() => onPageChange(0)}
          disabled={safePage <= 0}
          ariaLabel="First page"
          testId={`${testId}-first`}
        >
          «
        </PageButton>
        <PageButton
          onClick={() => onPageChange(safePage - 1)}
          disabled={safePage <= 0}
          ariaLabel="Previous page"
          testId={`${testId}-prev`}
        >
          ‹ Prev
        </PageButton>
        <span
          className="px-2 py-1 text-bny-slate"
          data-testid={`${testId}-page`}
        >
          Page {safePage + 1} of {pageCount}
        </span>
        <PageButton
          onClick={() => onPageChange(safePage + 1)}
          disabled={safePage >= pageCount - 1}
          ariaLabel="Next page"
          testId={`${testId}-next`}
        >
          Next ›
        </PageButton>
        <PageButton
          onClick={() => onPageChange(pageCount - 1)}
          disabled={safePage >= pageCount - 1}
          ariaLabel="Last page"
          testId={`${testId}-last`}
        >
          »
        </PageButton>
      </div>
    </nav>
  );
}

function PageButton({
  onClick,
  disabled,
  ariaLabel,
  children,
  testId,
}: {
  onClick: () => void;
  disabled: boolean;
  ariaLabel: string;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className="px-2 py-1 rounded-md border border-bny-mist bg-white text-bny-ink hover:bg-bny-paper disabled:text-bny-fog disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-bny-teal"
    >
      {children}
    </button>
  );
}
