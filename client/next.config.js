/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return [
      {
        source: '/',
        destination: '/welcome',
        permanent: false,
        has: [{ type: 'cookie', key: 'token', missing: true }],  // только если нет токена
      },
    ];
  },
};

module.exports = nextConfig;