import { defineConfig } from "orval"

export default defineConfig({
  observatory: {
    input: {
      target: "../backend/openapi/observatory-v1.json",
    },
    output: {
      target: "src/data/generated/validators.ts",
      client: "zod",
      mode: "single",
      clean: ["src/data/generated"],
      override: {
        zod: {
          generateEachHttpStatus: true,
          generateReusableSchemas: true,
          strict: {
            body: true,
            header: true,
            param: true,
            query: true,
            response: true,
          },
          variant: "mini",
          version: 4,
        },
      },
    },
  },
})
