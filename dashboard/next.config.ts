import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: {
    // Flat-config interop with eslint-config-next is still settling.
    // Phase 2 task: re-enable after upgrading or migrating to a shared flat preset.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
