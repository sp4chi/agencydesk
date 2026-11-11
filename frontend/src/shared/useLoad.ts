import { useCallback, useEffect, useState, type DependencyList } from "react";

import { ApiError } from "../api/client";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Load data from the API and expose loading / error / reload. */
export function useLoad<T>(load: () => Promise<T>, deps: DependencyList): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    load()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorText(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `load` is a new function every render; the caller's deps say when to re-run.
  }, [...deps, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload };
}

export function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Could not reach the server. Please try again.";
}
