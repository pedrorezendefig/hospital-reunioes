"use client";

import { useRef, useCallback, useEffect } from "react";

/**
 * Hook that returns a debounced version of the given callback.
 *
 * Consolidates the repeated pattern found in:
 *   - dashboard/page.tsx   (debounceRef + setTimeout on filter change, 300ms)
 *   - other filter-heavy pages with manual setTimeout/clearTimeout
 *
 * The returned function has the same signature as `callback` but delays
 * execution until `delay` ms have passed since the last invocation.
 * Pending timeouts are cleared on unmount.
 *
 * Usage:
 *   const debouncedFetch = useDebouncedCallback(() => {
 *     fetchAllData();
 *   }, 300);
 *
 *   useEffect(() => { debouncedFetch(); }, [filters, debouncedFetch]);
 */
export function useDebouncedCallback<
  T extends (...args: Parameters<T>) => void,
>(callback: T, delay: number): (...args: Parameters<T>) => void {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbackRef = useRef(callback);

  // Keep callback ref fresh to avoid stale closures
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const debouncedFn = useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
      }, delay);
    },
    [delay],
  );

  return debouncedFn;
}
