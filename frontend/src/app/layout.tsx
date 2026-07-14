import type { Metadata } from 'next';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import { Header } from '@/components/layout/Header';
import { ToastViewport } from '@/components/ui/Toast';
import '@/styles/globals.css';

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
      <body className="min-h-screen flex flex-col bg-background text-text">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <Header />
          <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
            {children}
          </main>
          <ToastViewport />
        </ThemeProvider>
      </body>
    </html>
  );
}
