import { useEffect, useRef, useState } from "react";

const roomCount = 12_288;

export function AtlasProbe() {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [duration, setDuration] = useState<number | null>(null);

  useEffect(() => {
    const surface = canvas.current;
    const context = surface?.getContext("2d");
    if (!surface || !context) return;
    const ratio = Math.max(1, window.devicePixelRatio);
    const width = surface.clientWidth;
    const height = surface.clientHeight;
    surface.width = width * ratio;
    surface.height = height * ratio;
    context.scale(ratio, ratio);
    const started = performance.now();
    context.fillStyle = "#0a0f14";
    context.fillRect(0, 0, width, height);
    context.fillStyle = "rgba(104, 225, 220, 0.52)";
    for (let index = 0; index < roomCount; index += 1) {
      const angle = index * 2.399963;
      const radius = Math.sqrt(index / roomCount) * Math.min(width, height) * 0.46;
      const x = width / 2 + Math.cos(angle) * radius;
      const y = height / 2 + Math.sin(angle) * radius;
      context.fillRect(x, y, 1.2, 1.2);
    }
    setDuration(performance.now() - started);
  }, []);

  return (
    <section className="atlas-probe" aria-labelledby="atlas-title">
      <header>
        <div>
          <p className="eyebrow">Renderer capacity probe</p>
          <h3 id="atlas-title">12,288-room atlas</h3>
        </div>
        <span>{duration === null ? "measuring" : `${duration.toFixed(1)} ms draw`}</span>
      </header>
      <canvas ref={canvas} aria-label="Atlas-scale renderer capacity probe" />
      <p>
        Synthetic positions test rendering capacity only. They are not game
        knowledge and never enter the evidence model.
      </p>
    </section>
  );
}
