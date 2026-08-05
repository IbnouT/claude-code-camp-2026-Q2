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
  const query = new URLSearchParams({
    player: session.player_id,
    session: session.id,
  });
  return `/sessions?${query.toString()}`;
}

export function sessionsHref(playerId?: string): string {
  const query = new URLSearchParams();
  if (playerId) query.set("player", playerId);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return `/sessions${suffix}`;
}

export function liveIdentity(location: RouteLocation): LiveRouteIdentity | null {
  if (location.pathname !== "/live") return null;
  const query = new URLSearchParams(location.search);
  const playerId = query.get("player")?.trim() ?? "";
  const sessionId = query.get("session")?.trim() ?? "";
  if (playerId === "" || sessionId === "") return null;
  return { playerId, sessionId };
}
