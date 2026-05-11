import { useQuery } from "@tanstack/react-query";
import { getRun, listRuns } from "./runs";
import { getPipeline, listPipelines } from "./pipelines";
import { getEmployee, getReview } from "./employees";
import { getSkill } from "./skills";

export const usePipelineQuery = (ddqId: string) =>
  useQuery({
    queryKey: ["pipeline", ddqId],
    queryFn: () => getPipeline(ddqId),
  });

export const usePipelinesIndexQuery = () =>
  useQuery({
    queryKey: ["pipelines"],
    queryFn: () => listPipelines(),
  });

export const useRunQuery = (runId: string) =>
  useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });

export const useRunsIndexQuery = () =>
  useQuery({
    queryKey: ["runs"],
    queryFn: () => listRuns(),
  });

export const useEmployeeQuery = (id: string) =>
  useQuery({
    queryKey: ["employee", id],
    queryFn: () => getEmployee(id),
  });

export const useReviewQuery = (id: string, period: string) =>
  useQuery({
    queryKey: ["review", id, period],
    queryFn: () => getReview(id, period),
  });

export const useSkillQuery = (skillId: string) =>
  useQuery({
    queryKey: ["skill", skillId],
    queryFn: () => getSkill(skillId),
  });
