"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AdminJobsFilters {
  status?: string;
  jurisdiction?: string;
  active_only?: boolean;
  stale_only?: boolean;
  limit?: number;
}

/** List query — polls every 5s when the active_only filter is on so the
 *  operator's view stays current while a job is running. Otherwise cached
 *  at the default staleTime. */
export function useAdminJobs(filters: AdminJobsFilters) {
  return useQuery({
    queryKey: ["admin-jobs", filters],
    queryFn: () => api.listAdminJobs(filters),
    refetchInterval: filters.active_only ? 5000 : false,
    refetchIntervalInBackground: false,
    staleTime: 5000,
  });
}

export function useAdminJob(jobId: string | null) {
  return useQuery({
    queryKey: ["admin-job", jobId],
    queryFn: () => api.getAdminJob(jobId!),
    enabled: !!jobId,
    staleTime: 5000,
  });
}

function useInvalidateJobs() {
  const qc = useQueryClient();
  return (jobId?: string) => {
    qc.invalidateQueries({ queryKey: ["admin-jobs"] });
    if (jobId) qc.invalidateQueries({ queryKey: ["admin-job", jobId] });
  };
}

export function useCancelJob() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: (job) => invalidate(job.id),
  });
}

export function useRetryJob() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (jobId: string) => api.retryJob(jobId),
    onSuccess: (job) => invalidate(job.id),
  });
}

export function useForceRerunJob() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (jobId: string) => api.forceRerunJob(jobId),
    onSuccess: (job) => invalidate(job.id),
  });
}
