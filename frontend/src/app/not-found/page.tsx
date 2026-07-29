import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center">
      <span className="font-display text-8xl font-bold text-accent/30">404</span>
      <h1 className="mt-4 font-display text-2xl font-semibold tracking-tight">
        頁面不存在
      </h1>
      <p className="mt-3 max-w-md text-sm text-textSecondary leading-relaxed">
        你找的頁面可能已被移除、名稱變更，或暫時無法使用。
      </p>
      <Link
        href="/"
        className="group mt-8 inline-flex items-center gap-2 bg-accent px-5 py-2.5 text-sm font-medium text-accentInk transition-colors hover:bg-accentStrong"
      >
        ← 返回首頁
      </Link>
    </div>
  );
}
