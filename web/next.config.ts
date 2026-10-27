import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Images come from the API through signed URLs; they are already resized server-side.
  images: { unoptimized: true },
};

export default config;
