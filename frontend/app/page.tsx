import { JurisdictionForm } from "@/components/JurisdictionForm";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-2xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Zoning Finder
          </h1>
          <p className="text-slate-500 text-base">
            Find vacant parcels zoned for self-storage, mini-warehouse, light
            industrial, or luxury garage condominium development — in minutes.
          </p>
        </div>

        {/* Search form */}
        <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <JurisdictionForm />
        </div>

        {/* Quick-start hint */}
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          <p className="font-semibold mb-1">Works with any US city or county</p>
          <ul className="space-y-1 text-emerald-700">
            <li>
              <span className="font-medium">City name —</span>{" "}
              <code className="rounded bg-emerald-100 px-1 py-0.5 font-mono text-xs">Draper, UT</code>
              {" "}or{" "}
              <code className="rounded bg-emerald-100 px-1 py-0.5 font-mono text-xs">Mesa, AZ</code>
              {" "}— auto-discovered via ArcGIS Hub
            </li>
            <li>
              <span className="font-medium">ArcGIS map URL —</span>{" "}
              paste a Web Map or direct FeatureServer link
            </li>
            <li>
              <span className="font-medium">Regrid fallback —</span>{" "}
              set <code className="rounded bg-emerald-100 px-1 py-0.5 font-mono text-xs">REGRID_API_KEY</code>{" "}
              for cities without public GIS
            </li>
          </ul>
        </div>
      </div>
    </main>
  );
}
