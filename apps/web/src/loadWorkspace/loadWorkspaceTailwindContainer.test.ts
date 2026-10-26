import { describe, expect, it } from "vitest";
import { readFileSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("Tailwind container queries for stops grid", () => {
  it("registers @tailwindcss/container-queries in tailwind config", () => {
    const cfg = readFileSync(resolve(__dirname, "../../tailwind.config.cjs"), "utf8");
    expect(cfg).toContain("@tailwindcss/container-queries");
  });

  it("stop grid class uses named container queries", () => {
    const form = readFileSync(resolve(__dirname, "LoadWorkspaceForm.tsx"), "utf8");
    expect(form).toContain("@container/stops");
    expect(form).toMatch(/@\[36rem\]\/stops:grid-cols-2/);
    expect(form).not.toMatch(/grid-cols-4/);
  });
});
