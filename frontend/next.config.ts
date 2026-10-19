import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // The sidebar's foot shows the API connection; keep the dev badge off it.
  devIndicators: { position: "bottom-right" },
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
