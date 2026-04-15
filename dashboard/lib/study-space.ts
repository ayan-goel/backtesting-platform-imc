// Client-side search-space validation. Mirrors the server-side rules in
// server/services/study_space.py so the form surfaces errors inline instead
// of on POST.

import type { ParamSpec, SearchSpace } from "@/lib/types";

export interface SpaceError {
  name: string;
  message: string;
}

export function validateSpace(space: SearchSpace): SpaceError[] {
  const errors: SpaceError[] = [];
  const names = Object.keys(space);
  if (names.length === 0) {
    errors.push({ name: "", message: "search space must not be empty" });
    return errors;
  }
  for (const name of names) {
    if (!name.trim()) {
      errors.push({ name, message: "param name must not be blank" });
      continue;
    }
    const spec = space[name];
    const err = validateSpec(spec);
    if (err) errors.push({ name, message: err });
  }
  return errors;
}

export function validateSpec(spec: ParamSpec): string | null {
  if (spec.type === "int") {
    if (!Number.isFinite(spec.low) || !Number.isFinite(spec.high)) {
      return "int low/high must be numbers";
    }
    if (spec.low > spec.high) return `int low (${spec.low}) > high (${spec.high})`;
    if (spec.step !== undefined && spec.step <= 0) return "int step must be > 0";
    return null;
  }
  if (spec.type === "float") {
    if (!Number.isFinite(spec.low) || !Number.isFinite(spec.high)) {
      return "float low/high must be numbers";
    }
    if (spec.low > spec.high) return `float low (${spec.low}) > high (${spec.high})`;
    if (spec.step !== undefined && spec.step !== null && spec.step <= 0) {
      return "float step must be > 0 if set";
    }
    return null;
  }
  if (spec.type === "categorical") {
    if (!spec.choices || spec.choices.length === 0) {
      return "categorical choices must not be empty";
    }
    return null;
  }
  return "unknown spec type";
}

export function parseChoices(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}
