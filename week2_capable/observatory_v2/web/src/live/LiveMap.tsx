import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { Snapshot } from "../contracts";
import type { LiveRouteIdentity } from "../routes";
import {
  buildMapGraph,
  canonicalNodeId,
  centerMapViewport,
  initialMapCamera,
  mapDragScale,
  mapRoomHeight,
  mapRoomWidth,
  type MapConnection,
  type MapPoint,
  type MapViewport,
} from "./mapModel";
import { LiveMapRoom } from "./LiveMapRoom";
import {
  selectedRoomFromLocation,
  syncSelectedRoomToLocation,
} from "./selectionUrl";

type Props = {
  identity: LiveRouteIdentity;
};

const defaultFrame = { width: 1_600, height: 900 };

type DragState = {
  pointerId: number;
  clientX: number;
  clientY: number;
  center: MapPoint;
};

export function LiveMap({ identity }: Props) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "reconnecting">(
    "loading",
  );
  const [frame, setFrame] = useState(defaultFrame);
  const [panCenter, setPanCenter] = useState<MapPoint | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(
    selectedRoomFromLocation,
  );
  const [dragging, setDragging] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<DragState | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let timer = 0;
    const load = () => {
      fetch(`/api/sessions/${encodeURIComponent(identity.sessionId)}/snapshot`, {
        cache: "no-store",
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Snapshot unavailable (${response.status})`);
          }
          return response.json() as Promise<Snapshot>;
        })
        .then((nextSnapshot) => {
          if (!isSnapshot(nextSnapshot)) {
            throw new Error("Snapshot returned an invalid world projection");
          }
          setSnapshot(nextSnapshot);
          setState("ready");
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setState("reconnecting");
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            timer = window.setTimeout(load, 2_000);
          }
        });
    };
    load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [identity.sessionId]);

  const graph = useMemo(() => {
    return buildMapGraph(
      snapshot?.world.nodes ?? [],
      snapshot?.world.edges ?? [],
    );
  }, [snapshot]);
  const beaconRoomIds = useMemo(() => {
    const rawNodes = new Map(
      (snapshot?.world.nodes ?? []).map((node) => [node.id, node]),
    );
    return new Set(
      (snapshot?.world.objective_beacons ?? []).flatMap((beacon) => {
        const node = rawNodes.get(beacon.node_id);
        return node === undefined ? [] : [canonicalNodeId(node)];
      }),
    );
  }, [snapshot]);
  const handleSelectRoom = useCallback((nodeId: string) => {
    setSelectedRoomId((current) => {
      const next = current === nodeId ? null : nodeId;
      syncSelectedRoomToLocation(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (svg === null || typeof ResizeObserver === "undefined") return;
    const updateFrame = () => {
      const bounds = svg.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return;
      setFrame((current) => {
        if (
          Math.abs(current.width - bounds.width) < 1
          && Math.abs(current.height - bounds.height) < 1
        ) {
          return current;
        }
        return { width: bounds.width, height: bounds.height };
      });
    };
    const observer = new ResizeObserver(updateFrame);
    observer.observe(svg);
    updateFrame();
    return () => observer.disconnect();
  }, [graph.rooms.length]);

  useEffect(() => {
    setPanCenter(null);
    setSelectedRoomId(selectedRoomFromLocation());
  }, [identity.sessionId]);

  if (snapshot === null) {
    return (
      <div className="live-map-message" role="status">
        {state === "reconnecting"
          ? "World evidence is reconnecting."
          : "Loading learned world…"}
      </div>
    );
  }

  if (graph.rooms.length === 0) {
    return (
      <div className="live-map-message" role="status">
        Waiting for the first observed room.
      </div>
    );
  }

  const roomById = new Map(
    graph.rooms.map((room) => [room.node.id, room.point]),
  );
  const camera = initialMapCamera(graph, frame.width, frame.height);
  const viewport = panCenter === null
    ? camera.viewport
    : centerMapViewport(graph, camera.viewport, panCenter);
  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!camera.panning) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      center: viewportCenter(viewport),
    };
    setDragging(true);
  };
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = svgRef.current;
    if (
      drag === null
      || drag.pointerId !== event.pointerId
      || svg === null
    ) {
      return;
    }
    const bounds = svg.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return;
    const horizontalScale = mapDragScale(graph.width, viewport.width);
    const verticalScale = mapDragScale(graph.height, viewport.height);
    setPanCenter({
      x: drag.center.x
        - (event.clientX - drag.clientX)
          * viewport.width
          / bounds.width
          * horizontalScale,
      y: drag.center.y
        - (event.clientY - drag.clientY)
          * viewport.height
          / bounds.height
          * verticalScale,
    });
  };
  const stopDragging = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return (
    <section className="live-map-stage" aria-label="Learned world map">
      <svg
        className={[
          "live-map",
          camera.panning ? "is-pannable" : "",
          dragging ? "is-dragging" : "",
        ].filter(Boolean).join(" ")}
        ref={svgRef}
        role="img"
        aria-label={[
          `Learned world, ${graph.rooms.length} rooms`,
          camera.panning ? "Drag to pan" : "",
        ].filter(Boolean).join(". ")}
        viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
      >
        <defs>
          <radialGradient id="live-current-room-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#4fd6c9" stopOpacity=".55" />
            <stop offset="100%" stopColor="#4fd6c9" stopOpacity="0" />
          </radialGradient>
        </defs>
        <g className="live-map-connections">
          {graph.connections.map((connection) => (
            <MapLink
              key={connection.id}
              connection={connection}
              source={roomById.get(connection.source)}
              target={roomById.get(connection.target)}
            />
          ))}
        </g>
        <g className="live-map-rooms">
          {graph.rooms.map(({ node, point }) => (
            <LiveMapRoom
              key={node.id}
              node={node}
              point={point}
              current={node.id === graph.currentRoomId}
              selected={node.id === selectedRoomId}
              combat={Boolean(
                snapshot.combat && node.id === graph.currentRoomId,
              )}
              beacon={beaconRoomIds.has(node.id)}
              onSelect={handleSelectRoom}
            />
          ))}
        </g>
      </svg>
      {camera.panning ? (
        <p className="live-map-pan-hint">Drag to explore the learned world.</p>
      ) : null}
      {state === "reconnecting" ? (
        <p className="live-map-connection-state" role="status">
          Showing the latest world while evidence reconnects.
        </p>
      ) : null}
    </section>
  );
}

function MapLink({
  connection,
  source,
  target,
}: {
  connection: MapConnection;
  source: MapPoint | undefined;
  target: MapPoint | undefined;
}) {
  if (source === undefined || target === undefined) {
    return null;
  }
  const start = {
    x: source.x + mapRoomWidth / 2,
    y: source.y + mapRoomHeight / 2,
  };
  const end = {
    x: target.x + mapRoomWidth / 2,
    y: target.y + mapRoomHeight / 2,
  };
  const path = connection.bent
    ? bentPath(start, end)
    : `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
  const className = [
    "live-map-link",
    connection.bent ? "is-bent" : "",
    connection.displacement ? "is-displacement" : "",
    connection.vertical ? "is-vertical" : "",
  ].filter(Boolean).join(" ");
  return (
    <g className={className}>
      <path d={path} />
    </g>
  );
}

function bentPath(source: MapPoint, target: MapPoint): string {
  const middleX = (source.x + target.x) / 2;
  const middleY = (source.y + target.y) / 2;
  const deltaX = target.x - source.x;
  const deltaY = target.y - source.y;
  const length = Math.max(Math.hypot(deltaX, deltaY), 1);
  const controlX = middleX - (deltaY / length) * 34;
  const controlY = middleY + (deltaX / length) * 34;
  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`;
}

function viewportCenter(viewport: MapViewport): MapPoint {
  return {
    x: viewport.x + viewport.width / 2,
    y: viewport.y + viewport.height / 2,
  };
}

function isSnapshot(value: unknown): value is Snapshot {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<Snapshot>;
  return typeof candidate.player_id === "string"
    && typeof candidate.world === "object"
    && candidate.world !== null
    && Array.isArray(candidate.world.nodes)
    && Array.isArray(candidate.world.edges);
}
