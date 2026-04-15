// Server-side API client. Called from Server Components + route handlers only.
// The X-API-Key is read from process.env and never sent to the browser.

import type {
  Batch,
  Dataset,
  EventRecord,
  McSimulation,
  RunSummary,
  Strategy,
  Study,
  StudyTrialSummary,
} from "@/lib/types";

const API_URL = process.env.PLATFORM_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.PLATFORM_API_KEY ?? "";

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      "X-API-Key": API_KEY,
    },
    cache: "no-store",
  });
}

export async function listRuns(skip = 0, limit = 50): Promise<RunSummary[]> {
  const res = await apiFetch(`/runs?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`listRuns failed: ${res.status}`);
  return (await res.json()) as RunSummary[];
}

export async function getRunSummary(runId: string): Promise<RunSummary> {
  const res = await apiFetch(`/runs/${encodeURIComponent(runId)}/summary`);
  if (!res.ok) throw new Error(`getRunSummary failed: ${res.status}`);
  return (await res.json()) as RunSummary;
}

export async function getRunEvents(
  runId: string,
  opts: { product?: string; tsFrom?: number; tsTo?: number; limit?: number } = {}
): Promise<EventRecord[]> {
  const params = new URLSearchParams();
  if (opts.product) params.set("product", opts.product);
  if (opts.tsFrom !== undefined) params.set("ts_from", String(opts.tsFrom));
  if (opts.tsTo !== undefined) params.set("ts_to", String(opts.tsTo));
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  const res = await apiFetch(
    `/runs/${encodeURIComponent(runId)}/events?${params.toString()}`
  );
  if (!res.ok) throw new Error(`getRunEvents failed: ${res.status}`);
  const text = await res.text();
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as EventRecord);
}

export async function listDatasets(): Promise<Dataset[]> {
  const res = await apiFetch("/datasets");
  if (!res.ok) throw new Error(`listDatasets failed: ${res.status}`);
  return (await res.json()) as Dataset[];
}

export async function listStrategies(): Promise<Strategy[]> {
  const res = await apiFetch("/strategies");
  if (!res.ok) throw new Error(`listStrategies failed: ${res.status}`);
  return (await res.json()) as Strategy[];
}

export async function listBatches(skip = 0, limit = 50): Promise<Batch[]> {
  const res = await apiFetch(`/batches?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`listBatches failed: ${res.status}`);
  return (await res.json()) as Batch[];
}

export async function getBatch(batchId: string): Promise<Batch> {
  const res = await apiFetch(`/batches/${encodeURIComponent(batchId)}`);
  if (!res.ok) throw new Error(`getBatch failed: ${res.status}`);
  return (await res.json()) as Batch;
}

export async function listStudies(skip = 0, limit = 50): Promise<Study[]> {
  const res = await apiFetch(`/studies?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`listStudies failed: ${res.status}`);
  return (await res.json()) as Study[];
}

export async function getStudy(studyId: string): Promise<Study> {
  const res = await apiFetch(`/studies/${encodeURIComponent(studyId)}`);
  if (!res.ok) throw new Error(`getStudy failed: ${res.status}`);
  return (await res.json()) as Study;
}

export async function listStudyTrials(studyId: string): Promise<StudyTrialSummary[]> {
  const res = await apiFetch(
    `/studies/${encodeURIComponent(studyId)}/trials`
  );
  if (!res.ok) throw new Error(`listStudyTrials failed: ${res.status}`);
  return (await res.json()) as StudyTrialSummary[];
}

export async function listMcSimulations(
  skip = 0,
  limit = 200
): Promise<McSimulation[]> {
  const res = await apiFetch(`/mc?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`listMcSimulations failed: ${res.status}`);
  return (await res.json()) as McSimulation[];
}

export async function getMcSimulation(mcId: string): Promise<McSimulation> {
  const res = await apiFetch(`/mc/${encodeURIComponent(mcId)}`);
  if (!res.ok) throw new Error(`getMcSimulation failed: ${res.status}`);
  return (await res.json()) as McSimulation;
}

export async function getMcPathCurve(
  mcId: string,
  index: number
): Promise<{ index: number; curve: number[] }> {
  const res = await apiFetch(
    `/mc/${encodeURIComponent(mcId)}/paths/${index}/curve`
  );
  if (!res.ok) throw new Error(`getMcPathCurve failed: ${res.status}`);
  return (await res.json()) as { index: number; curve: number[] };
}

export async function proxyToApi(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  return apiFetch(path, init);
}
