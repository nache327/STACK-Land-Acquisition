import { useEffect, useState } from "react";

/**
 * Debounce a value: returns `value` only after it has stopped changing
 * for `delayMs` milliseconds. Used by the dashboard map's bbox refetch
 * so a single drag/zoom gesture doesn't fire N intermediate searches.
 *
 * Each render where `value` changes resets the timer; on cleanup the
 * pending timer is cancelled so the consumer never sees a stale
 * value after unmount.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(handle);
  }, [value, delayMs]);

  return debounced;
}
