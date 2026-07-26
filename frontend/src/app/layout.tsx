import type { Metadata } from 'next';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import { Header } from '@/components/layout/Header';
import { ToastViewport } from '@/components/ui/Toast';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: 'Quant Backtest Platform',
  description: '極簡高性能量化回測與優化平台',
  appleWebApp: {
    capable: true,
    title: 'QuantPlatform',
    statusBarStyle: 'black-translucent',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW" suppressHydrationWarning>
      <head>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
      </head>
      <body className="min-h-screen flex flex-col bg-background text-text">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
          <Header />
          <main className="flex-1 w-full">
            {children}
          </main>
          <ToastViewport />
        </ThemeProvider>
      </body>
    </html>
  );
}
