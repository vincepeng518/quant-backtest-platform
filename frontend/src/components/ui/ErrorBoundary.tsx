'use client';

import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    // 僅記錄, 不向上拋 (避免整頁 Application error)
    if (typeof console !== 'undefined') {
      console.error('[ErrorBoundary]', error);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-xl border border-border/10 bg-surface/50 p-5">
            <p className="text-sm text-textSecondary">監控組件暫時無法顯示</p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
