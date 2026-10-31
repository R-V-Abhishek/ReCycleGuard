import { createContext, useContext, useEffect, useState } from "react";
import type { ApiClient } from "../api/client";

export interface Session {
  client: ApiClient;
  disconnect(): void;
}

// The session, including the bearer token, lives only in React state. A reload asks for it again.
export const SessionContext = createContext<Session | null>(null);

export function useClient(): ApiClient {
  const session = useContext(SessionContext);
  if (!session) throw new Error("No API session");
  return session.client;
}

export function useRoute(): string[] {
  const read = () => {
    try {
      return window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
    } catch {
      // A malformed percent escape in an external/bookmarked hash must not crash the app.
      return [];
    }
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(...parts: string[]) {
  window.location.hash = "/" + parts.map(encodeURIComponent).join("/");
}

export function href(...parts: string[]) {
  return "#/" + parts.map(encodeURIComponent).join("/");
}
