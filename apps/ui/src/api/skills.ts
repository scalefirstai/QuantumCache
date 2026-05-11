import type { SkillDetail } from "@/types/skill";
import { ApiError, get } from "./client";

/**
 * Production endpoint shape (proposed):
 *   GET /api/v1/skills/:skill_id  →  SkillDetail
 */
export async function getSkill(skillId: string): Promise<SkillDetail> {
  if (skillId !== "retrieval-hybrid") {
    throw new ApiError("Skill not found", 404, `/api/v1/skills/${skillId}`);
  }
  return get<SkillDetail>(
    `/api/v1/skills/${skillId}`,
    () =>
      import("@/mocks/fixtures/skill-retrieval.json").then((m) => ({
        default: m.default as unknown as SkillDetail,
      })),
  );
}
