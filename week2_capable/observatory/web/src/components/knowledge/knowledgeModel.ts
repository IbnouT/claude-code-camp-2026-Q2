import type {
  KnowledgeAssertion,
  PlayerKnowledge,
} from "../../data/knowledge";

export type KnowledgeLensId =
  | "overview"
  | "map"
  | "entities"
  | "progression"
  | "snapshots"
  | "history";

export type KnowledgeLayer = "learned" | "observer_truth" | "diff";

export function visibleAssertions(
  knowledge: PlayerKnowledge,
  layer: KnowledgeLayer,
  query: string,
): KnowledgeAssertion[] {
  const normalized = query.trim().toLocaleLowerCase();
  return knowledge.assertions.filter((item) => {
    const layerMatch = layer === "diff"
      ? Boolean(item.conflict_group)
      : item.layer === layer;
    if (!layerMatch) return false;
    if (!normalized) return true;
    return [
      item.subject,
      item.predicate,
      renderKnowledgeValue(item.value),
      item.confidence,
      item.status,
    ].some((value) => value.toLocaleLowerCase().includes(normalized));
  });
}

export function assertionCategory(
  assertion: KnowledgeAssertion,
): "map" | "entities" | "progression" {
  const subject = assertion.subject.toLocaleLowerCase();
  const predicate = assertion.predicate.toLocaleLowerCase();
  if (
    subject.startsWith("room:")
    || subject.startsWith("place:")
    || predicate.startsWith("exit.")
  ) return "map";
  if (
    subject.startsWith("entity:")
    || subject.startsWith("mob:")
    || subject.startsWith("object:")
    || subject.startsWith("npc:")
    || predicate.includes("sighting")
  ) return "entities";
  return "progression";
}

export function humanizeKnowledge(value: string): string {
  return value.replaceAll(":", " · ").replaceAll(".", " ");
}

export function renderKnowledgeValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value) ?? "undefined";
}

export function formatKnowledgeTime(value: number): string {
  return new Date(value * 1_000).toLocaleString();
}
