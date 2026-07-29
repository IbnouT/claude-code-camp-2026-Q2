import { decodeEvent, type EventEnvelope } from "./contracts";

export class EvidenceStreamDecoder {
  private remainder = "";
  private readonly decoder = new TextDecoder();

  push(chunk: Uint8Array): EventEnvelope[] {
    this.remainder += this.decoder.decode(chunk, { stream: true });
    return this.takeFrames();
  }

  finish(): EventEnvelope[] {
    this.remainder += this.decoder.decode();
    return this.takeFrames(true);
  }

  private takeFrames(flush = false): EventEnvelope[] {
    const normalized = this.remainder.replaceAll("\r\n", "\n");
    const parts = normalized.split("\n\n");
    this.remainder = flush ? "" : (parts.pop() ?? "");
    const frames = flush ? parts.filter(Boolean) : parts;
    return frames.flatMap((frame) => {
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      return data ? [decodeEvent(JSON.parse(data) as unknown)] : [];
    });
  }
}

export function decodeEvidenceText(text: string): EventEnvelope[] {
  const decoder = new EvidenceStreamDecoder();
  const body = new TextEncoder().encode(text);
  return [...decoder.push(body), ...decoder.finish()];
}
