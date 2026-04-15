"use client";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { ParamSpec, SearchSpace } from "@/lib/types";
import { parseChoices } from "@/lib/study-space";
import { cn } from "@/lib/utils";

export interface SpaceRow {
  name: string;
  spec: ParamSpec;
  choicesRaw?: string;
}

interface Props {
  rows: SpaceRow[];
  onChange: (rows: SpaceRow[]) => void;
  errorsByName: Record<string, string>;
}

const DEFAULT_INT: ParamSpec = { type: "int", low: 0, high: 5 };
const DEFAULT_FLOAT: ParamSpec = { type: "float", low: 0.0, high: 1.0 };
const DEFAULT_CAT: ParamSpec = { type: "categorical", choices: [] };

export function buildSearchSpace(rows: SpaceRow[]): SearchSpace {
  const out: SearchSpace = {};
  for (const row of rows) {
    if (!row.name.trim()) continue;
    if (row.spec.type === "categorical") {
      out[row.name] = {
        type: "categorical",
        choices: parseChoices(row.choicesRaw ?? ""),
      };
    } else {
      out[row.name] = row.spec;
    }
  }
  return out;
}

export function SearchSpaceBuilder({ rows, onChange, errorsByName }: Props) {
  function updateRow(i: number, patch: Partial<SpaceRow>) {
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  function updateSpec(i: number, patch: Partial<ParamSpec>) {
    const row = rows[i];
    onChange(
      rows.map((r, j) =>
        j === i ? { ...r, spec: { ...row.spec, ...patch } as ParamSpec } : r
      )
    );
  }

  function changeType(i: number, type: ParamSpec["type"]) {
    const next =
      type === "int" ? DEFAULT_INT : type === "float" ? DEFAULT_FLOAT : DEFAULT_CAT;
    onChange(
      rows.map((r, j) =>
        j === i
          ? { ...r, spec: { ...next }, choicesRaw: type === "categorical" ? r.choicesRaw ?? "" : undefined }
          : r
      )
    );
  }

  function addRow() {
    onChange([...rows, { name: "", spec: { ...DEFAULT_INT } }]);
  }

  function removeRow(i: number) {
    onChange(rows.filter((_, j) => j !== i));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
          search space
        </div>
        <button
          type="button"
          onClick={addRow}
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-accent"
        >
          + add param
        </button>
      </div>

      {rows.length === 0 && (
        <div className="rounded-card border border-dashed border-border p-4 text-xs text-muted-fg">
          no params yet — click &ldquo;add param&rdquo; to start
        </div>
      )}

      <div className="space-y-2">
        {rows.map((row, i) => {
          const err = errorsByName[row.name];
          return (
            <div
              key={i}
              className={cn(
                "rounded-card border border-border bg-surface-1/40 p-3",
                err && "border-sell/60 bg-sell/5"
              )}
            >
              <div className="grid grid-cols-12 items-end gap-2">
                <div className="col-span-3 flex flex-col gap-1">
                  <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                    name
                  </div>
                  <Input
                    mono
                    type="text"
                    value={row.name}
                    onChange={(e) => updateRow(i, { name: e.target.value })}
                    placeholder="edge"
                    className="h-7 text-xs"
                  />
                </div>

                <div className="col-span-2 flex flex-col gap-1">
                  <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                    type
                  </div>
                  <Select
                    mono
                    value={row.spec.type}
                    onChange={(e) =>
                      changeType(i, e.target.value as ParamSpec["type"])
                    }
                    className="h-7 text-xs"
                  >
                    <option value="int">int</option>
                    <option value="float">float</option>
                    <option value="categorical">categorical</option>
                  </Select>
                </div>

                {(row.spec.type === "int" || row.spec.type === "float") && (
                  <>
                    <div className="col-span-3 flex flex-col gap-1">
                      <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                        low
                      </div>
                      <Input
                        mono
                        type="number"
                        step={row.spec.type === "float" ? "any" : "1"}
                        value={row.spec.low}
                        onChange={(e) =>
                          updateSpec(i, { low: Number(e.target.value) })
                        }
                        className="h-7 text-xs"
                      />
                    </div>
                    <div className="col-span-3 flex flex-col gap-1">
                      <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                        high
                      </div>
                      <Input
                        mono
                        type="number"
                        step={row.spec.type === "float" ? "any" : "1"}
                        value={row.spec.high}
                        onChange={(e) =>
                          updateSpec(i, { high: Number(e.target.value) })
                        }
                        className="h-7 text-xs"
                      />
                    </div>
                  </>
                )}

                {row.spec.type === "categorical" && (
                  <div className="col-span-6 flex flex-col gap-1">
                    <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                      choices (comma separated)
                    </div>
                    <Input
                      mono
                      type="text"
                      value={row.choicesRaw ?? ""}
                      onChange={(e) =>
                        updateRow(i, { choicesRaw: e.target.value })
                      }
                      placeholder="mm, taker"
                      className="h-7 text-xs"
                    />
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  className="col-span-1 text-right text-lg leading-none text-muted-fg transition-colors duration-fast hover:text-sell"
                  aria-label={`remove ${row.name || "param"}`}
                >
                  ×
                </button>
              </div>
              {err && (
                <div className="mt-2 text-[11px] text-sell">{err}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
