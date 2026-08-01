import type { Session } from "./contracts";

export type LiveRouteIdentity = {
  playerId: string;
  sessionId: string;
};

type RouteLocation = Pick<Location, "pathname" | "search">;

export function liveHref(identity: LiveRouteIdentity): string {
  const query = new URLSearchParams({
    player: identity.playerId,
    session: identity.sessionId,
  });
  return `/live?${query.toString()}`;
}

type RecordedSession = Pick<Session, "id" | "player_id">;

export function recordedSessionHref(session: RecordedSession): string {
  return liveHref({
    playerId: session.player_id,
    sessionId: session.id,
  });
}

export function sessionsHref(playerId?: string): string {
  const query = new URLSearchParams({ space: "sessions" });
  if (playerId) query.set("player", playerId);
  return `http://127.0.0.1:8787/?${query.toString()}`;
}

export function liveIdentity(location: RouteLocation): LiveRouteIdentity | null {
  if (location.pathname !== "/live") return null;
  const query = new URLSearchParams(location.search);
  const playerId = query.get("player")?.trim() ?? "";
  const sessionId = query.get("session")?.trim() ?? "";
  if (playerId === "" || sessionId === "") return null;
  return { playerId, sessionId };
}
