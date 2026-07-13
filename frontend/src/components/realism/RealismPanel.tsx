'use client';

import React from 'react';
import { Input } from '@/components/ui/Input';

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
}

interface Props {
  state: RealismState;
  handlers: RealismHandlers;
  collapsed?: boolean;
}

export function RealismPanel({ state, handlers, collapsed = true }: Props) {
  const [open, setOpen] = React.useState(!collapsed);
  const s = state;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-sm font-semibold uppercase tracking-wider text-textSecondary">
          合約仿真 / Realism
        </span>
        <span className="font-mono text-xs text-textSecondary">{open ? '收起 ▲' : '展開 ▼'}</span>
      </button>
      <p className="mt-1 text-xs text-textSecondary">
        資金費率 / 槓桿強平 / maker-taker 費率與交易所延遲。全部關閉 = 舊版 1x spot。
      </p>

      {open && (
        <div className="mt-4 space-y-5">
          {/* Funding */}
          <div className="rounded-lg border border-border/10 p-4">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={s.enableFunding}
                onChange={(e) => handlers.setEnableFunding(e.target.checked)}
              />
              資金費率 (Funding Rate)
            </label>
            {s.enableFunding && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Input label="Interval (h)" type="number" value={s.fundingInterval}
                  onChange={(e) => handlers.setFundingInterval(Number(e.target.value))} />
                <Input label="Default Rate" type="number" step={0.00001} value={s.fundingRate}
                  onChange={(e) => handlers.setFundingRate(Number(e.target.value))} />
              </div>
            )}
          </div>

          {/* Perpetual */}
          <div className="rounded-lg border border-border/10 p-4">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={s.enablePerp}
                onChange={(e) => handlers.setEnablePerp(e.target.checked)}
              />
              永續合約 / 槓桿強平 (Perpetual)
            </label>
            {s.enablePerp && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Input label="Leverage" type="number" value={s.leverage}
                  onChange={(e) => handlers.setLeverage(Number(e.target.value))} />
                <Input label="Maint. Margin" type="number" step={0.0005} value={s.maintMargin}
                  onChange={(e) => handlers.setMaintMargin(Number(e.target.value))} />
              </div>
            )}
          </div>

          {/* Exchange */}
          <div className="rounded-lg border border-border/10 p-4">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={s.enableExchange}
                onChange={(e) => handlers.setEnableExchange(e.target.checked)}
              />
              交易所環境 (Maker/Taker + 滑價 + 延遲)
            </label>
            {s.enableExchange && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
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
                <label className="flex items-end gap-2 text-sm">
                  <input type="checkbox" checked={s.forceLimit}
                    onChange={(e) => handlers.setForceLimit(e.target.checked)} />
                  Force Limit (maker)
                </label>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
