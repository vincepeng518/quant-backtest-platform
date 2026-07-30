'use client';

import React from 'react';
import { Input } from '@/components/ui/Input';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';

export interface RealismState {
  enableFunding: boolean;
  fundingInterval: number;
  fundingRate: number;
  enablePerp: boolean;
  leverage: number;
  maintMargin: number;
  enableExchange: boolean;
  makerFee: number;
  takerFee: number;
  latencyBars: number;
  bookSlippage: number;
  makerProbability: number;
  forceLimit: boolean;
  enableExec?: boolean;
  execSlippage?: number;
  execFillProb?: number;
  execLatency?: number;
}

export interface RealismHandlers {
  setEnableFunding: (v: boolean) => void;
  setFundingInterval: (v: number) => void;
  setFundingRate: (v: number) => void;
  setEnablePerp: (v: boolean) => void;
  setLeverage: (v: number) => void;
  setMaintMargin: (v: number) => void;
  setEnableExchange: (v: boolean) => void;
  setMakerFee: (v: number) => void;
  setTakerFee: (v: number) => void;
  setLatencyBars: (v: number) => void;
  setBookSlippage: (v: number) => void;
  setMakerProbability: (v: number) => void;
  setForceLimit: (v: boolean) => void;
  setEnableExec?: (v: boolean) => void;
  setExecSlippage?: (v: number) => void;
  setExecFillProb?: (v: number) => void;
  setExecLatency?: (v: number) => void;
}

interface Props {
  state: RealismState;
  handlers: RealismHandlers;
  collapsed?: boolean;
}

function SectionCard({
  color,
  title,
  checked,
  onChange,
  children,
}: {
  color: string;
  title: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-xl border border-white/[0.08] bg-surface2/40 backdrop-blur-sm p-4 transition-all hover:border-white/[0.15]">
      <div className={`absolute left-0 top-0 bottom-0 w-0.5 rounded-l-xl ${color}`} />
      <div className="pl-3">
        <div className="flex items-center gap-2">
          <ToggleSwitch
            checked={checked}
            onChange={onChange}
            badge={checked ? 'active' : 'off'}
          />
          <span className="text-sm font-medium text-text">{title}</span>
        </div>
        {checked && (
          <div className="mt-3 animate-[fadeIn_200ms_ease-out]">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

export function RealismPanel({ state, handlers, collapsed = true }: Props) {
  const [open, setOpen] = React.useState(!collapsed);
  const s = state;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left min-h-[44px]"
      >
        <span className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
          合約仿真 / Realism
        </span>
        <span className="font-mono text-xs text-textSecondary">{open ? '▲ 收起' : '▼ 展開'}</span>
      </button>
      <p className="mt-1 text-xs text-textSecondary">
        資金費率 / 槓桿強平 / maker-taker 費率與交易所延遲。全部關閉 = 舊版 1x spot。
      </p>

      {open && (
        <div className="mt-4 space-y-4 animate-[fadeIn_200ms_ease-out]">
          <SectionCard
            color="bg-sky-400/60"
            title="資金費率 (Funding Rate)"
            checked={s.enableFunding}
            onChange={handlers.setEnableFunding}
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Input label="Interval (h)" type="number" value={s.fundingInterval}
                onChange={(e) => handlers.setFundingInterval(Number(e.target.value))} />
              <Input label="Default Rate" type="number" step={0.00001} value={s.fundingRate}
                onChange={(e) => handlers.setFundingRate(Number(e.target.value))} />
            </div>
          </SectionCard>

          <SectionCard
            color="bg-violet-400/60"
            title="永續合約 / 槓桿強平 (Perpetual)"
            checked={s.enablePerp}
            onChange={handlers.setEnablePerp}
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Input label="Leverage" type="number" value={s.leverage}
                onChange={(e) => handlers.setLeverage(Number(e.target.value))} />
              <Input label="Maint. Margin" type="number" step={0.0005} value={s.maintMargin}
                onChange={(e) => handlers.setMaintMargin(Number(e.target.value))} />
            </div>
          </SectionCard>

          <SectionCard
            color="bg-orange-400/50"
            title="交易所環境 (Maker/Taker + 滑價 + 延遲)"
            checked={s.enableExchange}
            onChange={handlers.setEnableExchange}
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Input label="Maker Fee" type="number" step={0.0001} value={s.makerFee}
                onChange={(e) => handlers.setMakerFee(Number(e.target.value))} />
              <Input label="Taker Fee" type="number" step={0.0001} value={s.takerFee}
                onChange={(e) => handlers.setTakerFee(Number(e.target.value))} />
              <Input label="Latency (bars)" type="number" value={s.latencyBars}
                onChange={(e) => handlers.setLatencyBars(Number(e.target.value))} />
              <Input label="Book Slippage" type="number" step={0.0001} value={s.bookSlippage}
                onChange={(e) => handlers.setBookSlippage(Number(e.target.value))} />
              <Input label="Maker Prob" type="number" step={0.05} value={s.makerProbability}
                onChange={(e) => handlers.setMakerProbability(Number(e.target.value))} />
              <label className="flex items-center gap-2 text-sm text-textSecondary">
                <input type="checkbox" checked={s.forceLimit}
                  onChange={(e) => handlers.setForceLimit(e.target.checked)}
                  className="accent-accent" />
                Force Limit (maker)
              </label>
            </div>
          </SectionCard>

          <SectionCard
            color="bg-emerald-400/50"
            title="成交真實度 (Execution: 滑點 + 成交概率 + 延遲)"
            checked={s.enableExec ?? false}
            onChange={(v) => handlers.setEnableExec?.(v)}
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Input label="Slippage %" type="number" step={0.0005} value={s.execSlippage ?? 0}
                onChange={(e) => handlers.setExecSlippage?.(Number(e.target.value))} />
              <Input label="Fill Prob (limit)" type="number" step={0.05} value={s.execFillProb ?? 1}
                onChange={(e) => handlers.setExecFillProb?.(Number(e.target.value))} />
              <Input label="Latency (ms)" type="number" value={s.execLatency ?? 0}
                onChange={(e) => handlers.setExecLatency?.(Number(e.target.value))} />
            </div>
          </SectionCard>
        </div>
      )}

      <style jsx global>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
