import type { NextConfig } from "next";

const basePath = "/bloque";

const nextConfig: NextConfig = {
  basePath,
  output: "standalone",
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

export default nextConfig;
