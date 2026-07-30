import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test } from "vitest";
import { IncidentWorkflow } from "./IncidentWorkflow";

beforeEach(() => {
  localStorage.clear();
});

test("keeps annotations attached to stable evidence while replay moves", async () => {
  const user = userEvent.setup();
  const view = renderWorkflow("gateway:4");
  await user.click(screen.getByRole("button", { name: /Incident/ }));
  await user.type(
    screen.getByRole("textbox", {
      name: "Add context to the selected evidence",
    }),
    "The position became ambiguous here.",
  );
  await user.click(screen.getByRole("button", { name: "Attach note" }));
  expect(screen.getByText("The position became ambiguous here.")).toBeVisible();

  view.rerender(workflow("gateway:5"));
  expect(screen.queryByText("The position became ambiguous here."))
    .not.toBeInTheDocument();

  view.rerender(workflow("gateway:4"));
  expect(screen.getByText("The position became ambiguous here.")).toBeVisible();

  view.unmount();
  renderWorkflow("gateway:4");
  await user.click(screen.getByRole("button", { name: /Incident/ }));
  expect(screen.getByText("The position became ambiguous here.")).toBeVisible();
});

function renderWorkflow(selectedRecordId: string) {
  return render(workflow(selectedRecordId));
}

function workflow(selectedRecordId: string) {
  return (
    <IncidentWorkflow
      diagnosticId={null}
      initialAnnotations={[]}
      lens="evidence"
      mode="recorded"
      redactionPolicy={null}
      runId="run-1"
      selectedRecordId={selectedRecordId}
      sourceVersions={{}}
    />
  );
}
