/** @type {import('next').NextConfig} */
const nextConfig = {
  // Strict mode for better React dev experience
  reactStrictMode: true,

  // COOP enables SharedArrayBuffer for MapLibre Web Workers.
  // COEP (require-corp) is intentionally omitted — it would block cross-origin
  // tile requests to OpenFreeMap/other tile CDNs that don't set CORP headers.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },

  // Transpile MapLibre GL JS for Next.js bundler compatibility
  transpilePackages: ["maplibre-gl"],


};

module.exports = nextConfig;

