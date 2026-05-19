import type {
  BulkReviewRequest,
  RemediationCommand,
  RescoreRequest,
  SourceReviewRequest,
} from "@/lib/schemas";

/** Translate a backend RemediationStep `command` into a typed call against
 *  the api client. Pure function — no I/O.
 *
 *  Hardened against the obvious "remote-told-me-to-curl-anything" foot-gun:
 *  only paths that match an allow-list of known operator endpoints are
 *  dispatchable. Anything else returns `{kind: "unsupported"}` and the
 *  step renders as CLI-only (the operator copies the `cli_hint`).
 */

type Dispatch =
  | {
      kind: "discover";
      countyId: string;
      municipalityNames: string[];
    }
  | {
      kind: "ingest";
      countyId: string;
      sourceIds: string[];
    }
  | {
      kind: "review";
      jurisdictionId: string;
      sourceId: string;
      body: SourceReviewRequest;
    }
  | {
      kind: "bulk_review";
      jurisdictionId: string;
      body: BulkReviewRequest;
    }
  | {
      kind: "rescore";
      jurisdictionId: string;
      body: RescoreRequest;
    }
  | {
      kind: "refresh_coverage";
      jurisdictionId: string | null;
    }
  | {
      kind: "unsupported";
      reason: string;
    };

const JID_RE = "([0-9a-f-]{36})";
const ANY_PATH_SEG = "([^/?]+)";

const PATTERNS = {
  discover: new RegExp(`^/api/jurisdictions/${JID_RE}/_discover-municipal-zoning$`),
  ingest: new RegExp(`^/api/jurisdictions/${JID_RE}/_ingest-municipal-zoning$`),
  review: new RegExp(
    `^/api/jurisdictions/${JID_RE}/_sources/${ANY_PATH_SEG}/_review$`,
  ),
  bulkReview: new RegExp(
    `^/api/jurisdictions/${JID_RE}/_sources/_bulk-review$`,
  ),
  rescore: new RegExp(
    `^/api/jurisdictions/${JID_RE}/_rescore-stale-sources$`,
  ),
  refresh: /^\/api\/admin\/coverage\/refresh(?:\?.*)?$/,
};

export function dispatchPlanCommand(cmd: RemediationCommand): Dispatch {
  const method = (cmd.method ?? "").toUpperCase();
  const path = cmd.path ?? "";

  if (method !== "POST") {
    return {
      kind: "unsupported",
      reason: `Only POST commands run from the UI (got ${method}).`,
    };
  }

  let m: RegExpMatchArray | null;

  m = path.match(PATTERNS.discover);
  if (m) {
    const body = (cmd.body ?? {}) as { municipality_names?: unknown };
    const names = Array.isArray(body.municipality_names)
      ? (body.municipality_names as unknown[]).filter(
          (x): x is string => typeof x === "string",
        )
      : [];
    if (names.length === 0) {
      return {
        kind: "unsupported",
        reason: "discover command missing municipality_names",
      };
    }
    return { kind: "discover", countyId: m[1], municipalityNames: names };
  }

  m = path.match(PATTERNS.ingest);
  if (m) {
    const body = (cmd.body ?? {}) as { source_ids?: unknown };
    const ids = Array.isArray(body.source_ids)
      ? (body.source_ids as unknown[]).filter(
          (x): x is string => typeof x === "string",
        )
      : [];
    if (ids.length === 0) {
      return {
        kind: "unsupported",
        reason: "ingest command missing source_ids",
      };
    }
    return { kind: "ingest", countyId: m[1], sourceIds: ids };
  }

  m = path.match(PATTERNS.review);
  if (m) {
    const body = (cmd.body ?? {}) as Partial<SourceReviewRequest>;
    if (
      !body.action
      || !["verify", "reject", "needs_review", "unverify"].includes(body.action)
    ) {
      return {
        kind: "unsupported",
        reason: "review command missing valid action",
      };
    }
    return {
      kind: "review",
      jurisdictionId: m[1],
      sourceId: m[2],
      body: {
        action: body.action,
        notes: body.notes ?? null,
        rejected_reason: body.rejected_reason ?? null,
      },
    };
  }

  m = path.match(PATTERNS.bulkReview);
  if (m) {
    const body = (cmd.body ?? {}) as Partial<BulkReviewRequest>;
    if (
      !body.action
      || !["verify", "reject", "needs_review"].includes(body.action)
      || !Array.isArray(body.source_ids)
    ) {
      return {
        kind: "unsupported",
        reason: "bulk_review command missing valid action/source_ids",
      };
    }
    return {
      kind: "bulk_review",
      jurisdictionId: m[1],
      body: {
        action: body.action as BulkReviewRequest["action"],
        source_ids: body.source_ids as string[],
        rejected_reason: body.rejected_reason ?? null,
      },
    };
  }

  m = path.match(PATTERNS.rescore);
  if (m) {
    const body = (cmd.body ?? {}) as Partial<RescoreRequest>;
    // Default to a safe dry-run if the backend forgot to set it.
    return {
      kind: "rescore",
      jurisdictionId: m[1],
      body: {
        dry_run: body.dry_run ?? true,
        source_ids: body.source_ids ?? null,
        max_rows: body.max_rows ?? 200,
        only_status: body.only_status ?? null,
        stale_only: body.stale_only ?? true,
        concurrency: body.concurrency ?? 8,
      },
    };
  }

  if (PATTERNS.refresh.test(path)) {
    // Extract optional jurisdiction_id from query or query object.
    const qid =
      (cmd.query?.jurisdiction_id as string | undefined)
      ?? new URL(`http://x${path}`).searchParams.get("jurisdiction_id");
    return { kind: "refresh_coverage", jurisdictionId: qid ?? null };
  }

  return {
    kind: "unsupported",
    reason: `Path ${path} is not on the UI allow-list — use the cli_hint instead.`,
  };
}

/** Operator-facing one-liner used for the button label. */
export function describeDispatch(d: Dispatch): string {
  switch (d.kind) {
    case "discover":
      return `Discover sources for ${d.municipalityNames.join(", ")}`;
    case "ingest":
      return `Ingest ${d.sourceIds.length} verified source${d.sourceIds.length === 1 ? "" : "s"}`;
    case "review":
      return `${d.body.action} source`;
    case "bulk_review":
      return `${d.body.action} ${d.body.source_ids.length} source${d.body.source_ids.length === 1 ? "" : "s"}`;
    case "rescore":
      return d.body.dry_run ? "Rescore dry-run" : "Apply rescore";
    case "refresh_coverage":
      return "Refresh coverage audit";
    case "unsupported":
      return "Use CLI";
  }
}
