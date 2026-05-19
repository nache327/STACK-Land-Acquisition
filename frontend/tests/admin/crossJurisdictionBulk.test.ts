import {
  groupByJurisdiction,
  runCrossJurisdictionBulk,
} from "@/lib/admin/crossJurisdictionBulk";

describe("groupByJurisdiction", () => {
  it("partitions selections by jurisdiction_id", () => {
    const out = groupByJurisdiction([
      { source_id: "a", jurisdiction_id: "j1" },
      { source_id: "b", jurisdiction_id: "j2" },
      { source_id: "c", jurisdiction_id: "j1" },
    ]);
    expect(Object.keys(out).sort()).toEqual(["j1", "j2"]);
    expect(out.j1).toEqual(["a", "c"]);
    expect(out.j2).toEqual(["b"]);
  });
});

describe("runCrossJurisdictionBulk", () => {
  it("calls send once per jurisdiction with 50-id chunking inside each", async () => {
    const j1 = Array.from({ length: 73 }, (_, i) => `j1-${i}`);
    const j2 = Array.from({ length: 5 }, (_, i) => `j2-${i}`);
    const selections = [
      ...j1.map((id) => ({ source_id: id, jurisdiction_id: "j1" })),
      ...j2.map((id) => ({ source_id: id, jurisdiction_id: "j2" })),
    ];
    const calls: Array<{ jid: string; size: number }> = [];
    const send = jest.fn(async (jid: string, chunk: string[]) => {
      calls.push({ jid, size: chunk.length });
      return { updated: chunk.length, skipped: 0 };
    });

    const res = await runCrossJurisdictionBulk({ selections, send });

    expect(send).toHaveBeenCalledTimes(3); // j1 split into 2 chunks, j2 fits in 1
    expect(calls.filter((c) => c.jid === "j1").map((c) => c.size)).toEqual([
      50, 23,
    ]);
    expect(calls.filter((c) => c.jid === "j2").map((c) => c.size)).toEqual([5]);

    expect(res.updated).toBe(78);
    expect(res.skipped).toBe(0);
    expect(res.jurisdictions_touched).toBe(2);
    expect(res.per_jurisdiction).toEqual([
      { jurisdiction_id: "j1", updated: 73, skipped: 0 },
      { jurisdiction_id: "j2", updated: 5, skipped: 0 },
    ]);
  });

  it("aggregates skipped counts across jurisdictions", async () => {
    const send = jest
      .fn()
      .mockResolvedValueOnce({ updated: 5, skipped: 1 })
      .mockResolvedValueOnce({ updated: 3, skipped: 0 });
    const res = await runCrossJurisdictionBulk({
      selections: [
        { source_id: "a", jurisdiction_id: "j1" },
        { source_id: "b", jurisdiction_id: "j2" },
      ],
      send,
    });
    expect(res).toMatchObject({
      updated: 8,
      skipped: 1,
      jurisdictions_touched: 2,
    });
  });

  it("returns zero counts for an empty selection without calling send", async () => {
    const send = jest.fn();
    const res = await runCrossJurisdictionBulk({ selections: [], send });
    expect(send).not.toHaveBeenCalled();
    expect(res.updated).toBe(0);
    expect(res.jurisdictions_touched).toBe(0);
  });
});
