"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

interface AuthState {
  token: string | null;
  userId: string | null;
  userEmail: string | null;
  loading: boolean;
}

/**
 * Hook that consolidates the repeated auth session pattern:
 *   createClient() -> getSession() -> extract token/userId/userEmail
 *
 * Runs once on mount. Sets loading=false when done.
 *
 * Usage:
 *   const { token, userId, userEmail, loading } = useAuth();
 */
export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({
    token: null,
    userId: null,
    userEmail: null,
    loading: true,
  });

  useEffect(() => {
    async function init() {
      const supabase = createClient();

      // Some pages check getUser() first (e.g. reunioes/[id]) to validate
      // the user is still authenticated before trusting getSession().
      // Defensive: re-fetches user from /auth/v1/user to detect remote logout (session can be cached but user revoked).
      const {
        data: { user },
        error,
      } = await supabase.auth.getUser();

      if (error || !user) {
        setState({ token: null, userId: null, userEmail: null, loading: false });
        return;
      }

      const {
        data: { session },
      } = await supabase.auth.getSession();

      setState({
        token: session?.access_token ?? null,
        userId: user.id,
        userEmail: user.email ?? null,
        loading: false,
      });
    }

    init();
  }, []);

  return state;
}

/**
 * Non-hook version for use inside event handlers and callbacks.
 *
 * Mirrors the `getToken()` helper found in reunioes/[id]/page.tsx:
 *   getUser() -> getSession() -> return access_token
 *
 * Usage:
 *   async function handleClick() {
 *     const token = await getAuthToken();
 *     fetch("/api/...", { headers: { Authorization: `Bearer ${token}` } });
 *   }
 */
export async function getAuthToken(): Promise<string | undefined> {
  const supabase = createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) return undefined;

  const {
    data: { session },
  } = await supabase.auth.getSession();

  return session?.access_token;
}
