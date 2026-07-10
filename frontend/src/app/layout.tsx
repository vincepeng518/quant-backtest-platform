import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import { Header } from '@/components/layout/Header';
import '@/styles/globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });

export const metadata: Metadata = {
  title: 'Quant Backtest Platform',
  description: '極簡高性能量化回測與優化平台',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW" suppressHydrationWarning>
      <body className={`${inter.variable} min-h-screen flex flex-col bg-background text-text`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <Header />
          <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
