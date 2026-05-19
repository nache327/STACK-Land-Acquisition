import {
  BULK_REVIEW_MAX_PER_REQUEST,
  chunkSourceIds,
  runBulkReview,
} from "@/lib/admin/bulkReview";

describe("chunkSourceIds", () => {
  it("returns a single chunk when ids fit under the cap", () => {
    const ids = Array.from({ length: 12 }, (_, i) => `id-${i}`);
    expect(chunkSourceIds(ids)).toEqual([ids]);
  });

  it("splits at the 50-id backend cap", () => {
    const ids = Array.from({ length: 123 }, (_, i) => `id-${i}`);
    const chunks = chunkSourceIds(ids);
    expect(chunks).toHaveLength(3);
    expect(chunks[0]).toHaveLength(BULK_REVIEW_MAX_PER_REQUEST);
    expect(chunks[1]).toHaveLength(BULK_REVIEW_MAX_PER_REQUEST);
    expect(chunks[2]).toHaveLength(23);
    expect(chunks.flat()).toEqual(ids);
  });

  it("returns one empty chunk when given no ids", () => {
    expect(chunkSourceIds([])).toEqual([]);
  });
});

describe("runBulkReview", () => {
  it("calls send once per chunk and aggregates the result", async () => {
    const ids = Array.from({ length: 73 }, (_, i) => `id-${i}`);
    const calls: string[][] = [];
    const send = jest.fn(async (chunk: string[]) => {
      calls.push(chunk);
      return { updated: chunk.length, skipped: 0 };
    });

    const res = await runBulkReview({ ids, action: "verify", send });

    expect(send).toHaveBeenCalledTimes(2);
    expect(calls[0]).toHaveLength(50);
    expect(calls[1]).toHaveLength(23);
    expect(res).toEqual({ updated: 73, skipped: 0 });
  });

  it("propagates skipped counts from each chunk", async () => {
    const ids = Array.from({ length: 60 }, (_, i) => `id-${i}`);
    const send = jest
      .fn()
      .mockResolvedValueOnce({ updated: 50, skipped: 0 })
      .mockResolvedValueOnce({ updated: 7, skipped: 3 });

    const res = await runBulkReview({ ids, action: "reject", send });
    expect(res).toEqual({ updated: 57, skipped: 3 });
  });
});
