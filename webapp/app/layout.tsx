import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '2027 SWE Jobs',
  description:
    'Summer 2027 internships, off-cycle co-ops, and new grad software engineering jobs',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
