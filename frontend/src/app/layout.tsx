import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'DisasterVision',
  description: 'Futuristic disaster analysis dashboard',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang='en'
      className={[geistSans.variable, geistMono.variable, 'h-full', 'antialiased'].join(' ')}
    >
      <body className='min-h-screen bg-[#030303] text-white selection:bg-white/20 selection:text-white'>
        <div className='bg-grid pointer-events-none fixed inset-0 opacity-40' />
        <div className='noise fixed inset-0 opacity-[0.02]' />
        <div className='relative flex min-h-screen flex-col'>{children}</div>
      </body>
    </html>
  );
}
