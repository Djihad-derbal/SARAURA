import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API prints the PDF Report from http://127.0.0.1:3000 (SARS_FRONTEND_URL); in dev, Next.js blocks its
  // client scripts for any origin but localhost unless it is listed here, so the Report never became ready.
  allowedDevOrigins: ["127.0.0.1"],
  cacheComponents: true,
  partialPrefetching: true,
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
