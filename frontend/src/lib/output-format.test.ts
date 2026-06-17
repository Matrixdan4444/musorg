import { describe, expect, it } from "vitest";
import { collapseDuplicateLeadingYear } from "@/lib/output-format";

describe("collapseDuplicateLeadingYear", () => {
  it("collapses a duplicated leading year", () => {
    expect(collapseDuplicateLeadingYear("2024 - 2024 - начало")).toBe("2024 - начало");
  });

  it("leaves a single leading year untouched", () => {
    expect(collapseDuplicateLeadingYear("2024 - начало")).toBe("2024 - начало");
  });

  it("does not touch an album that is just a year", () => {
    expect(collapseDuplicateLeadingYear("1984")).toBe("1984");
  });

  it("does not collapse two different leading years", () => {
    expect(collapseDuplicateLeadingYear("2024 - 1999 Remaster")).toBe("2024 - 1999 Remaster");
  });
});
