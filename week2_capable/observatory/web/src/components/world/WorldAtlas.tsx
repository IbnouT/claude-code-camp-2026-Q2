import { Database, Layers3, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useAtlas } from "../../data/useAtlas";

export function WorldAtlas() {
  const [zone, setZone] = useState<number | null>(null);
  const { atlas, error } = useAtlas(zone);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [frameMs, setFrameMs] = useState<number | null>(null);
  const items = useMemo(
    () => atlas?.level === "overview" ? atlas.zones : atlas?.nodes ?? [],
    [atlas],
  );

  useEffect(() => {
    const target = canvas.current;
    if (target === null || atlas === null || !atlas.available) return;
    const draw = () => {
      const started = performance.now();
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(320, target.clientWidth);
      const height = Math.max(280, target.clientHeight);
      target.width = Math.floor(width * ratio);
      target.height = Math.floor(height * ratio);
      const context = target.getContext("2d");
      if (context === null) return;
      context.scale(ratio, ratio);
      context.clearRect(0, 0, width, height);
      const styles = getComputedStyle(target);
      const cyan = styles.getPropertyValue("--color-cyan").trim() || "#48d8d8";
      const muted = styles.getPropertyValue("--color-muted").trim() || "#82919e";
      const line = styles.getPropertyValue("--color-line-strong").trim() || "#33424e";
      const text = styles.getPropertyValue("--color-text").trim() || "#edf4f6";
      context.font = "10px ui-monospace, monospace";
      context.textAlign = "center";
      if (atlas.level === "overview") {
        const columns = Math.max(4, Math.ceil(Math.sqrt(atlas.zones.length * 1.8)));
        atlas.zones.forEach((item, index) => {
          const column = index % columns;
          const row = Math.floor(index / columns);
          const x = 42 + column * ((width - 84) / Math.max(1, columns - 1));
          const rows = Math.ceil(atlas.zones.length / columns);
          const y = 46 + row * ((height - 92) / Math.max(1, rows - 1));
          const radius = 8 + Math.min(17, Math.sqrt(item.room_count) * 1.6);
          context.beginPath();
          context.fillStyle = `${cyan}2b`;
          context.strokeStyle = cyan;
          context.lineWidth = 1.5;
          context.arc(x, y, radius, 0, Math.PI * 2);
          context.fill();
          context.stroke();
          context.fillStyle = text;
          context.fillText(`Z${item.zone}`, x, y + radius + 13);
          context.fillStyle = muted;
          context.fillText(`${item.room_count}`, x, y + 3);
        });
      } else {
        const nodes = atlas.nodes;
        const columns = Math.max(8, Math.ceil(Math.sqrt(nodes.length * 1.7)));
        const byVnum = new Map(nodes.map((item, index) => [item.vnum, index]));
        const point = (index: number) => ({
          x: 24 + (index % columns) * ((width - 48) / Math.max(1, columns - 1)),
          y: 24 + Math.floor(index / columns) * 30,
        });
        context.strokeStyle = line;
        context.lineWidth = 0.7;
        nodes.forEach((item, index) => {
          const start = point(index);
          Object.values(item.exits).forEach((targetVnum) => {
            const targetIndex = byVnum.get(targetVnum);
            if (targetIndex === undefined) return;
            const end = point(targetIndex);
            context.beginPath();
            context.moveTo(start.x, start.y);
            context.lineTo(end.x, end.y);
            context.stroke();
          });
        });
        nodes.forEach((_item, index) => {
          const position = point(index);
          context.beginPath();
          context.fillStyle = cyan;
          context.arc(position.x, position.y, 2.6, 0, Math.PI * 2);
          context.fill();
        });
      }
      requestAnimationFrame(() => {
        setFrameMs(Number((performance.now() - started).toFixed(2)));
      });
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(target);
    return () => observer.disconnect();
  }, [atlas]);

  if (error !== null) {
    return <AtlasGap detail={error} />;
  }
  if (atlas === null) {
    return <div className="atlas-loading">Loading observer atlas…</div>;
  }
  if (!atlas.available) {
    return <AtlasGap detail={atlas.detail} />;
  }

  return (
    <div className="world-atlas">
      <div className="world-atlas-summary">
        <span>
          <small>Observer truth · quarantined</small>
          <strong>
            {atlas.level === "overview"
              ? `${atlas.room_count.toLocaleString()} rooms`
              : `Zone ${atlas.selected_zone} · ${atlas.nodes.length} rooms`}
          </strong>
        </span>
        <dl>
          <div><dt>Edges</dt><dd>{atlas.edge_count.toLocaleString()}</dd></div>
          <div><dt>Zones</dt><dd>{atlas.zone_count}</dd></div>
          <div><dt>Duplicate titles</dt><dd>{atlas.duplicate_title_count}</dd></div>
          <div><dt>Load</dt><dd>{atlas.load_ms.toFixed(1)} ms</dd></div>
          <div>
            <dt>Frame</dt>
            <dd data-testid="atlas-frame">
              {frameMs?.toFixed(1) ?? "…"} ms
            </dd>
          </div>
          <div><dt>Memory</dt><dd>{formatBytes(atlas.memory_bytes)}</dd></div>
        </dl>
        {zone !== null ? (
          <button type="button" onClick={() => setZone(null)}>
            <ZoomOut size={13} aria-hidden="true" />
            All zones
          </button>
        ) : null}
      </div>
      <div className="world-atlas-canvas">
        <canvas
          aria-label={
            atlas.level === "overview"
              ? `Observer atlas overview, ${atlas.zone_count} zone clusters`
              : `Observer atlas zone ${atlas.selected_zone}, ${atlas.nodes.length} rooms`
          }
          ref={canvas}
          role="img"
        />
      </div>
      <p className="world-atlas-boundary">
        <Layers3 size={14} aria-hidden="true" />
        {atlas.detail}
      </p>
      <details className="world-table atlas-table">
        <summary>Explore the atlas as a structured list</summary>
        <div role="list">
          {atlas.level === "overview"
            ? atlas.zones.map((item) => (
              <div key={item.id} role="listitem">
                <button
                  type="button"
                  onClick={() => setZone(item.zone)}
                >
                  <span>Zone {item.zone}</span>
                  <small>
                    {item.room_count} rooms · {item.edge_count} exits ·{" "}
                    {item.duplicate_title_count} duplicate titles
                  </small>
                </button>
              </div>
            ))
            : atlas.nodes.map((item) => (
              <div className="atlas-room-row" key={item.id} role="listitem">
                <span>{item.title}</span>
                <small>#{item.vnum} · {Object.keys(item.exits).join(", ") || "no exits"}</small>
              </div>
            ))}
        </div>
      </details>
      <span className="world-atlas-lod">
        <Database size={12} aria-hidden="true" />
        Canvas LOD · {items.length} rendered items · zero room DOM nodes on canvas
      </span>
    </div>
  );
}

function AtlasGap({ detail }: { detail: string }) {
  return (
    <div className="world-explorer-empty">
      <Layers3 size={24} aria-hidden="true" />
      <strong>Observer atlas unavailable</strong>
      <span>{detail}</span>
    </div>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}
