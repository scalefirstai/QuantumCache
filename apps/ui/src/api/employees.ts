import type { EmployeeConsole } from "@/types/employee";
import type { PerformanceReview } from "@/types/review";
import { ApiError, get } from "./client";

/**
 * Production endpoint shapes (proposed):
 *   GET /api/v1/employees/:id              → EmployeeConsole
 *   GET /api/v1/employees/:id/reviews/:p   → PerformanceReview
 */
export async function getEmployee(id: string): Promise<EmployeeConsole> {
  if (id !== "aria") {
    throw new ApiError("Employee not found", 404, `/api/v1/employees/${id}`);
  }
  return get<EmployeeConsole>(
    `/api/v1/employees/${id}`,
    () =>
      import("@/mocks/fixtures/employee.json").then((m) => ({
        default: m.default as unknown as EmployeeConsole,
      })),
  );
}

export async function getReview(
  id: string,
  period: string,
): Promise<PerformanceReview> {
  if (id !== "aria" || period !== "q1-2026") {
    throw new ApiError(
      "Review not found",
      404,
      `/api/v1/employees/${id}/reviews/${period}`,
    );
  }
  return get<PerformanceReview>(
    `/api/v1/employees/${id}/reviews/${period}`,
    () =>
      import("@/mocks/fixtures/review-q1.json").then((m) => ({
        default: m.default as unknown as PerformanceReview,
      })),
  );
}
