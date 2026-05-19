import type { BulkReviewAction, BulkReviewResponse } from "@/lib/schemas";

export const BULK_REVIEW_MAX_PER_REQUEST = 50;

export function chunkSourceIds(
  ids: string[],
  size: number = BULK_REVIEW_MAX_PER_REQUEST,
): string[][] {
  if (size <= 0) return [ids];
  const chunks: string[][] = [];
  for (let i = 0; i < ids.length; i += size) {
    chunks.push(ids.slice(i, i + size));
  }
  return chunks;
}

interface RunArgs {
  ids: string[];
  action: BulkReviewAction;
  rejectedReason?: string | null;
  send: (chunk: string[]) => Promise<BulkReviewResponse>;
}

/** Fan out a list of source IDs across as many bulk-review requests as needed
 *  (backend cap = 50 per call) and aggregate the response. Sequential rather
 *  than parallel — keeps the DB write contention low at operator scale. */
export async function runBulkReview({
  ids,
  send,
}: RunArgs): Promise<BulkReviewResponse> {
  let updated = 0;
  let skipped = 0;
  for (const chunk of chunkSourceIds(ids)) {
    const res = await send(chunk);
    updated += res.updated;
    skipped += res.skipped;
  }
  return { updated, skipped };
}
