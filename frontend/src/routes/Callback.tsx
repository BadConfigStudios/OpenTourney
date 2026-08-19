import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext";

export function Callback() {
  const navigate = useNavigate();
  const { completeSignIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    completeSignIn()
      .then(() => navigate("/", { replace: true }))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Sign-in failed");
      });
    // Deliberately run once on mount only: re-running on every render would
    // replay the Authorization Code exchange, which Zitadel only accepts once.
    // The useRef guard prevents React 18 StrictMode's double-invocation in dev.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="p-8 text-center text-red-600">
        Sign-in failed: {error}.{" "}
        <a href="/" className="underline">
          Try again
        </a>
        .
      </div>
    );
  }

  return <div className="p-8 text-center text-gray-500">Completing sign-in…</div>;
}
