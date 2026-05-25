"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useAdminCoverage() {
  return useQuery({
    queryKey: ["admin-coverage"],
    queryFn: () => api.listAdminCoverage(),
    staleTime: 60 * 1000,
  });
}
