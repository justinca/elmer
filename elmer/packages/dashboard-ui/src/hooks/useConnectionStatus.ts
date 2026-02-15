import { useQuery } from "@tanstack/react-query"
import { getHealth } from "@/lib/api"
import { queryKeys } from "@/lib/queryKeys"
import { STALE_TIMES } from "@/lib/queryClient"

export function useConnectionStatus() {
  const { isSuccess } = useQuery({
    queryKey: queryKeys.health.core(),
    queryFn: () => getHealth().then((r) => r.data),
    staleTime: STALE_TIMES.health,
    refetchInterval: 30_000,
    retry: 1,
  })
  return isSuccess
}
