import type { NextConfig } from 'next';
import path from 'path';
import { fileURLToPath } from 'url';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // listings.json lives one level up; keep file tracing scoped to the repo root
  outputFileTracingRoot: path.join(rootDir, '..'),
};

export default nextConfig;
