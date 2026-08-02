import { readFileSync } from "node:fs"

const openapi = JSON.parse(
  readFileSync("../backend/openapi/observatory-v1.json", "utf8")
)
const validators = readFileSync("src/data/generated/validators.ts", "utf8")

function pascal(value) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

const failures = []
const operationIds = new Set()

for (const [path, pathItem] of Object.entries(openapi.paths)) {
  for (const [method, operation] of Object.entries(pathItem)) {
    const operationId = operation.operationId
    if (operationIds.has(operationId)) {
      failures.push(`duplicate operationId ${operationId}`)
    }
    operationIds.add(operationId)

    for (const [status, response] of Object.entries(operation.responses)) {
      const hasJson = Object.keys(response.content ?? {}).some((contentType) =>
        contentType.includes("json")
      )
      if (hasJson) {
        const name = `${pascal(operationId)}${status}Response`
        if (!validators.includes(`export const ${name} =`)) {
          failures.push(
            `${method.toUpperCase()} ${path} ${status}: missing generated validator`
          )
        }
      }
    }

    if (operation.requestBody !== undefined) {
      const name = `${pascal(operationId)}Body`
      if (!validators.includes(`export const ${name} =`)) {
        failures.push(
          `${method.toUpperCase()} ${path}: missing request body validator`
        )
      }
    }
  }
}

for (const schemaName of Object.keys(openapi.components?.schemas ?? {})) {
  if (
    !validators.includes(`export const ${schemaName} =`) &&
    !validators.includes(`export const ${schemaName}:`)
  ) {
    failures.push(`component ${schemaName}: missing generated validator`)
  }
  if (!validators.includes(`export type ${schemaName}Output =`)) {
    failures.push(`component ${schemaName}: missing generated output type`)
  }
}

if (failures.length > 0) {
  throw new Error(`Contract coverage failed:\n${failures.join("\n")}`)
}

console.log(
  `Contract coverage passed (${operationIds.size} operations with status-specific validators and generated component types).`
)
