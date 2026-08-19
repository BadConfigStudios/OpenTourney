import { UserManager, type User } from "oidc-client-ts";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useConfig } from "../config/ConfigProvider";
import type { PersonaRole } from "../config/types";

interface AuthValue {
  currentUser: { role: PersonaRole };
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
  completeSignIn: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return value;
}

// The subset of oidc-client-ts's UserManager this app actually calls -- kept
// narrow so tests can supply a plain object instead of a real UserManager
// (which needs a live authority to construct meaningfully).
export interface MinimalUserManager {
  getUser(): Promise<User | null>;
  signinRedirect(): Promise<void>;
  signinRedirectCallback(): Promise<User>;
  removeUser(): Promise<void>;
}

function deriveRole(user: User): PersonaRole {
  const roles = Array.isArray(user.profile.roles) ? (user.profile.roles as string[]) : [];
  if (roles.includes("organizer")) return "organizer";
  if (roles.includes("scorekeeper")) return "scorekeeper";
  // No recognized role (or none at all) degrades to the least-privileged view,
  // matching how every role-gated route already falls through to the player
  // view for a non-organizer/non-scorekeeper persona.
  return "player";
}

type SessionState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "authenticated"; user: User };

export function AuthProvider({
  children,
  userManagerOverride,
}: {
  children: ReactNode;
  userManagerOverride?: MinimalUserManager;
}) {
  const config = useConfig();

  const userManager = useMemo<MinimalUserManager>(
    () =>
      userManagerOverride ??
      new UserManager({
        authority: config.oidcAuthority,
        client_id: config.oidcClientId,
        redirect_uri: `${window.location.origin}/callback`,
        response_type: "code",
        // The reserved urn:zitadel:iam:org:project:id:{projectId}:aud scope
        // makes Zitadel include the project ID itself in the token's aud
        // claim, alongside the requesting client_id -- required because the
        // backend validates aud against secrets.oidcAudience, which is set
        // to this same project ID (see DEVELOPMENT.md).
        scope: `openid profile email urn:zitadel:iam:org:project:id:${config.oidcProjectId}:aud`,
        loadUserInfo: true,
        // No silent_redirect_uri is wired up (no hidden iframe target), so
        // disable oidc-client-ts's default automatic silent renewal --
        // leaving it enabled would attempt a silent renew near token expiry
        // that always fails silently; the app instead falls back to a full
        // page redirect via handleSessionExpired on actual expiry.
        automaticSilentRenew: false,
      }),
    [config, userManagerOverride],
  );

  const [state, setState] = useState<SessionState>({ status: "loading" });
  const redirecting = useRef(false);

  useEffect(() => {
    let cancelled = false;
    userManager.getUser().then((user) => {
      if (cancelled) return;
      setState(user && !user.expired ? { status: "authenticated", user } : { status: "unauthenticated" });
    });
    return () => {
      cancelled = true;
    };
  }, [userManager]);

  const completeSignIn = useCallback(async () => {
    const user = await userManager.signinRedirectCallback();
    setState({ status: "authenticated", user });
  }, [userManager]);

  const handleSessionExpired = useCallback(async () => {
    if (redirecting.current) return;
    redirecting.current = true;
    setState({ status: "unauthenticated" });
    await userManager.removeUser();
    await userManager.signinRedirect();
  }, [userManager]);

  if (state.status === "loading") {
    return <div className="p-8 text-center text-gray-500">Loading…</div>;
  }

  if (state.status === "unauthenticated") {
    // The post-redirect callback needs a provider in the tree to call
    // completeSignIn() through, even though no user is authenticated yet.
    // Callback.tsx is the only consumer mounted during this window and it
    // never reads currentUser, so the placeholder role below is never observed.
    if (window.location.pathname === "/callback") {
      const callbackValue: AuthValue = {
        currentUser: { role: "player" },
        apiFetch: () => Promise.reject(new Error("apiFetch called before sign-in completed")),
        completeSignIn,
      };
      return <AuthContext.Provider value={callbackValue}>{children}</AuthContext.Provider>;
    }
    return (
      <div className="flex min-h-screen items-center justify-center">
        <button
          className="rounded bg-blue-600 px-4 py-2 text-white"
          onClick={() => userManager.signinRedirect()}
        >
          Log in
        </button>
      </div>
    );
  }

  const { user } = state;
  const authValue: AuthValue = {
    currentUser: { role: deriveRole(user) },
    apiFetch: async (path: string, init: RequestInit = {}) => {
      if (user.expired) {
        await handleSessionExpired();
        throw new Error("session expired");
      }
      const response = await fetch(path, {
        ...init,
        headers: {
          ...init.headers,
          Authorization: `Bearer ${user.access_token}`,
          Accept: "application/json",
        },
      });
      if (response.status === 401) {
        await handleSessionExpired();
      }
      return response;
    },
    completeSignIn,
  };

  return <AuthContext.Provider value={authValue}>{children}</AuthContext.Provider>;
}
