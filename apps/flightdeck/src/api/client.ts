// The control path (ADR 0032, 0034): a thin typed client over qdt-server's HTTP API. Every body is a
// schema object from the generated src/schema/api.ts. This is Flight Deck's only channel besides the
// Dataset stream (rule 8): it never holds an instrument or a registry.
import type {
  AnalysisResult,
  CalibrationNode,
  DeviceRecord,
  ExecutionPlan,
  MeasurementRecord,
  MethodRequest,
  MethodSpec,
  NodeOutcome,
  ReplayRequest,
  Run,
  RunRequest,
  StandConfig,
  StreamInfo,
  SweepDefinition,
  TuneUp,
  TuneUpRequest,
} from "../schema/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

export interface RecordFilters {
  device_id?: string;
  definition_name?: string;
  campaign?: string;
}

type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export class ApiClient {
  constructor(
    readonly base: string,
    private readonly fetchFn: Fetch = (i, init) => fetch(i, init),
  ) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { "content-type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const r = await this.fetchFn(this.base + path, init);
    if (!r.ok) {
      let detail = r.statusText;
      try {
        const j = (await r.json()) as { detail?: unknown };
        if (j.detail !== undefined) detail = describeDetail(j.detail);
      } catch {
        /* no JSON body */
      }
      throw new ApiError(r.status, detail);
    }
    return (await r.json()) as T;
  }

  stand(): Promise<StandConfig> {
    return this.call("GET", "/stand");
  }
  devices(): Promise<DeviceRecord[]> {
    return this.call("GET", "/devices");
  }
  stream(): Promise<StreamInfo> {
    return this.call("GET", "/stream");
  }
  methods(): Promise<MethodSpec[]> {
    return this.call("GET", "/methods");
  }
  compile(definition: SweepDefinition): Promise<ExecutionPlan> {
    return this.call("POST", "/sweeps/compile", definition);
  }
  startRun(request: RunRequest): Promise<Run> {
    return this.call("POST", "/runs", request);
  }
  /** Queued: aborted at once. Running: stops between frames and is recorded as aborted; poll `run`. */
  abort(runId: string): Promise<Run> {
    return this.call("POST", `/runs/${encodeURIComponent(runId)}/abort`);
  }
  runs(): Promise<Run[]> {
    return this.call("GET", "/runs");
  }
  run(runId: string): Promise<Run> {
    return this.call("GET", `/runs/${runId}`);
  }
  records(filters: RecordFilters = {}): Promise<MeasurementRecord[]> {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) if (v) q.set(k, v);
    const s = q.toString();
    return this.call("GET", `/records${s ? `?${s}` : ""}`);
  }
  record(recordId: string): Promise<MeasurementRecord> {
    return this.call("GET", `/records/${recordId}`);
  }
  analyse(recordId: string, request: MethodRequest): Promise<AnalysisResult> {
    return this.call("POST", `/records/${recordId}/results`, request);
  }
  results(recordId: string): Promise<AnalysisResult[]> {
    return this.call("GET", `/results?record_id=${encodeURIComponent(recordId)}`);
  }
  result(resultId: string): Promise<AnalysisResult> {
    return this.call("GET", `/results/${resultId}`);
  }
  replay(request: ReplayRequest): Promise<StreamInfo> {
    return this.call("POST", "/stream/replay", request);
  }
  /** The calibration nodes this server offers, built for its stand's sequencer (ADR 0050). */
  nodes(): Promise<CalibrationNode[]> {
    return this.call("GET", "/nodes");
  }
  startTuneUp(request: TuneUpRequest): Promise<TuneUp> {
    return this.call("POST", "/tuneups", request);
  }
  tuneups(): Promise<TuneUp[]> {
    return this.call("GET", "/tuneups");
  }
  tuneup(tuneupId: string): Promise<TuneUp> {
    return this.call("GET", `/tuneups/${encodeURIComponent(tuneupId)}`);
  }
  /** Stops between nodes: the node running now finishes and is judged; poll `tuneup`. */
  stopTuneUp(tuneupId: string): Promise<TuneUp> {
    return this.call("POST", `/tuneups/${encodeURIComponent(tuneupId)}/stop`);
  }
  outcomes(tuneupId: string): Promise<NodeOutcome[]> {
    return this.call("GET", `/outcomes?tuneup_id=${encodeURIComponent(tuneupId)}`);
  }
}

/** A FastAPI error detail as one readable line: a string as is; a validation error list (422) as its
 * messages, without pydantic's "Value error, " prefix and the echoed input. */
export function describeDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((e) => {
      const { msg, loc } = (e ?? {}) as { msg?: unknown; loc?: unknown };
      if (typeof msg !== "string") return JSON.stringify(e);
      const where = Array.isArray(loc) ? loc.filter((p) => p !== "body").join(".") : "";
      return `${where ? `${where}: ` : ""}${msg.replace(/^Value error, /, "")}`;
    });
    return msgs.join("; ");
  }
  return JSON.stringify(detail);
}

/** The API base: `?api=` overrides the default local server. */
export function apiBase(params: URLSearchParams): string {
  return (params.get("api") ?? "http://127.0.0.1:8700").replace(/\/$/, "");
}
