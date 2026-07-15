import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '2027 Tech Jobs — SWE, PM, Data, Quant & Cyber Internships and New Grad',
  description:
    'Curated list of Summer 2027 internships, off-cycle co-ops, and 2027 new grad roles in software engineering, product management, data science, ML/AI, quantitative research, cybersecurity, DevOps, and adjacent technical fields. Updated hourly.',
  keywords: [
    '2027 internships', 'software engineering internship 2027', 'summer 2027 internship',
    'new grad 2027', 'SWE internship', 'PM internship 2027', 'data science internship 2027',
    'quant internship 2027', 'ML internship 2027', 'AI internship 2027',
    'cybersecurity internship 2027', 'tech jobs 2027', 'computer science internship 2027',
    'entry level software engineer 2027', 'new grad software engineer',
    'off-cycle internship', 'co-op 2027', 'fall 2026 internship',
  ],
  openGraph: {
    title: '2027 Tech Jobs — SWE, PM, Data, Quant & Cyber',
    description:
      'Curated Summer 2027 internships, off-cycle co-ops, and new grad roles in software engineering, PM, data, ML/AI, quant, and cybersecurity. Updated hourly.',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: '2027 Tech Jobs',
    description:
      'Summer 2027 internships & new grad roles in SWE, PM, data, quant, and cyber. Updated hourly.',
  },
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
