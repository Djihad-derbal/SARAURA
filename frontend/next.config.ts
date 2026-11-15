import type { NextConfig } from "next";

// Where the SARAURA API listens on this machine; /api/* on the website is forwarded there, so one public address
// (e.g. a Cloudflare tunnel) serves both the website and the API. Set NEXT_PUBLIC_API_URL=/api to use it.
const API_INTERNAL = process.env.SARS_API_INTERNAL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // The API prints the PDF Report from http://127.0.0.1:3000 (SARS_FRONTEND_URL); in dev, Next.js blocks its
  // client scripts for any origin but localhost unless it is listed here, so the Report never became ready.
  // *.trycloudflare.com: Cloudflare quick tunnels used to let testers open the app from their own laptops.
  allowedDevOrigins: ["127.0.0.1", "*.trycloudflare.com"],
  cacheComponents: true,
  partialPrefetching: true,
  rewrites: async () => [{ source: "/api/:path*", destination: `${API_INTERNAL}/:path*` }],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
