import { JurisdictionForm } from "@/components/JurisdictionForm";

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#070d1a]">

      {/* Background gradient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 h-[600px] w-[900px] -translate-x-1/2 rounded-full bg-blue-600/10 blur-3xl" />
        <div className="absolute top-1/3 -left-40 h-[400px] w-[600px] rounded-full bg-indigo-600/8 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-[400px] w-[500px] rounded-full bg-blue-800/10 blur-3xl" />
        {/* Subtle grid texture */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />
      </div>

      {/* Content */}
      <div className="relative flex min-h-screen flex-col items-center justify-center px-4 py-16">

        {/* Logo + wordmark */}
        <div className="mb-10 flex flex-col items-center gap-5">
          <div className="flex items-center gap-3">
            <ParcelLogicMark size={44} />
            <span className="text-2xl font-bold tracking-tight text-white">
              ParcelLogic
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-0.5 text-xs font-medium text-blue-300">
              Site Selection Intelligence
            </span>
          </div>
        </div>

        {/* Headline */}
        <div className="mb-10 max-w-2xl text-center">
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl">
            Find every parcel.{" "}
            <span className="bg-gradient-to-r from-blue-400 to-blue-300 bg-clip-text text-transparent">
              Skip the manual work.
            </span>
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-slate-400">
            Scan any US city for vacant parcels zoned for your development type — self-storage,
            mini-warehouse, light industrial, or luxury garage condos — in under two minutes.
          </p>
        </div>

        {/* Form card */}
        <div className="w-full max-w-xl">
          <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-8 shadow-2xl backdrop-blur-sm">
            <JurisdictionForm />
          </div>

          {/* Capability pills */}
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {[
              "Any US city or county",
              "ArcGIS Hub auto-discovery",
              "GIS parcel data",
              "Zoning matrix",
              "Flood + wetlands overlay",
            ].map((label) => (
              <span
                key={label}
                className="rounded-full border border-slate-700 bg-slate-800/50 px-3 py-1 text-xs text-slate-400"
              >
                {label}
              </span>
            ))}
          </div>
        </div>

      </div>
    </main>
  );
}

function ParcelLogicMark({ size = 36 }: { size?: number }) {
  const gap = Math.round(size * 0.1);
  const cell = Math.round((size - gap * 3) / 2);
  return (
    <div
      style={{ width: size, height: size }}
      className="flex-shrink-0 overflow-hidden rounded-xl bg-blue-600 shadow-lg shadow-blue-900/40"
    >
      <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
        <rect x="5" y="5" width="11" height="11" rx="2" fill="white" opacity="0.95" />
        <rect x="20" y="5" width="11" height="11" rx="2" fill="white" opacity="0.45" />
        <rect x="5" y="20" width="11" height="11" rx="2" fill="white" opacity="0.45" />
        <rect x="20" y="20" width="11" height="11" rx="2" fill="white" opacity="0.95" />
      </svg>
    </div>
  );
}
