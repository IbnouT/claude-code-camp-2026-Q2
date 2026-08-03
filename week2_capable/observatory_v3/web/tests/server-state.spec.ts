import { expect, test } from "@playwright/test"

const capabilities = {
  features: ["live", "replay"],
  sources: [
    {
      contract_digest: null,
      detail: "Registered sessions are discoverable",
      id: "gateway",
      label: "Gateway journals",
      state: "ready",
    },
    {
      contract_digest: null,
      detail: "Not configured",
      id: "knowledge",
      label: "Knowledge store",
      state: "disabled",
    },
  ],
  version: 1,
  voice: {
    detail: "Voice is disabled",
    enabled: false,
    endpoint_template: null,
    max_characters: 400,
  },
} as const

test("capabilities fetch, validate, cache, and render through one shared request", async ({
  page,
}) => {
  let requestCount = 0
  await page.route("**/api/v1/capabilities", async (route) => {
    requestCount += 1
    await route.fulfill({ json: capabilities, status: 200 })
  })

  await page.goto("/review")

  await expect(
    page.getByRole("heading", { name: "Typed server state" })
  ).toBeVisible()
  await expect(page.getByTestId("capabilities-state")).toHaveText("ready")
  await expect(page.getByText("Gateway journals")).toBeVisible()
  await expect(page.getByText("Knowledge store")).toBeVisible()
  expect(requestCount).toBe(1)
})

test("capabilities validation failure renders a typed non-retried state", async ({
  page,
}) => {
  let requestCount = 0
  await page.route("**/api/v1/capabilities", async (route) => {
    requestCount += 1
    await route.fulfill({ json: { features: ["live"] }, status: 200 })
  })

  await page.goto("/review")

  await expect(page.getByTestId("capabilities-state")).toHaveText(
    "validation error"
  )
  expect(requestCount).toBe(1)
})
