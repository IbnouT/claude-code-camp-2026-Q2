import { describe, expect, it } from "vitest";
import type { KnowledgeAssertion } from "../../data/knowledge";
import {
  assertionCategory,
  isMilestoneAssertion,
} from "./knowledgeModel";

function assertion(
  subject: string,
  predicate: string,
): KnowledgeAssertion {
  return {
    assertion_id: `${subject}:${predicate}`,
    fact_id: `${subject}:${predicate}`,
    subject,
    predicate,
    value: true,
    layer: "learned",
    status: "current",
    confidence: "high",
    current: true,
    conflict_group: null,
    evidence: [],
  };
}

describe("milestone knowledge classification", () => {
  it.each([
    ["player:poucet", "milestone.reached_bakery"],
    ["player:poucet", "objective.completed"],
    ["player:poucet", "level_up"],
    ["quest:newbie", "status"],
  ])("classifies %s %s as a milestone", (subject, predicate) => {
    const item = assertion(subject, predicate);
    expect(isMilestoneAssertion(item)).toBe(true);
    expect(assertionCategory(item)).toBe("milestones");
  });

  it("keeps ordinary vitals in progression", () => {
    const item = assertion("player:poucet", "vitals.hit");
    expect(isMilestoneAssertion(item)).toBe(false);
    expect(assertionCategory(item)).toBe("progression");
  });
});
