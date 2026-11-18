
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ChartPayload } from '../lib/api'
import { formatNumber } from '../lib/api'

const PALETTE = [
  '#6366F1',
  '#06B6D4',
  '#A78BFA',
  '#10B981',
  '#F59E0B',
  '#F472B6',
  '#FB7185',
  '#38BDF8',
  '#A3E635',
  '#C084FC',
]

const AXIS = {
  stroke: '#94A3B8',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
  tickMargin: 10,
}

const GRID = {
  stroke: 'rgba(148,163,184,0.13)',
  strokeDasharray: '4 5',
  vertical: false,
}

const TOOLTIP = {
  contentStyle: {
    backgroundColor: '#111827',
    border: '1px solid rgba(148,163,184,0.25)',
    borderRadius: 12,
    padding: '10px 14px',
    boxShadow: '0 12px 35px rgba(0,0,0,0.35)',
    color: '#F8FAFC',
    fontSize: 12,
  },
  labelStyle: {
    color: '#CBD5E1',
    fontWeight: 700,
    marginBottom: 6,
  },
  itemStyle: {
    color: '#F8FAFC',
    paddingTop: 3,
    paddingBottom: 3,
  },
  cursor: {
    fill: 'rgba(148,163,184,0.08)',
  },
}

const LEGEND = {
  wrapperStyle: {
    fontSize: 11,
    color: '#CBD5E1',
    paddingTop: 12,
  },
}

function Empty({ note }: { note?: string }) {
  return (
    <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-700/70 bg-slate-900/30 p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-800 text-2xl text-slate-400">
        ∅
      </div>
      <p className="text-sm font-medium text-slate-300">
        {note ?? 'No plottable data available'}
      </p>
      <p className="text-xs text-slate-500">
        Try selecting a different column or chart type.
      </p>
    </div>
  )
}

function ChartFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative w-full overflow-hidden rounded-2xl border border-white/[0.07] bg-gradient-to-br from-slate-900/70 via-slate-950/40 to-indigo-950/20 p-3 sm:p-4">
      {children}
    </div>
  )
}

export function ChartRenderer({
  chart,
  height = 340,
}: {
  chart: ChartPayload
  height?: number
}) {
  const data = chart.data ?? []

  if (!data.length && chart.chart_type !== 'box' && chart.chart_type !== 'correlation_heatmap') {
    return <Empty />
  }

  switch (chart.chart_type) {
    case 'histogram':
      return (
        <ChartFrame>
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data} margin={{ top: 18, right: 12, bottom: 28, left: 0 }} barCategoryGap="18%">
              <defs>
                <linearGradient id="histogramGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity={1} />
                  <stop offset="100%" stopColor="#6366F1" stopOpacity={0.65} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} angle={-30} textAnchor="end" interval="preserveStartEnd" height={58} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} formatter={(v: any) => [formatNumber(v), 'Rows']} />
              <Bar dataKey="value" fill="url(#histogramGradient)" radius={[7, 7, 0, 0]} maxBarSize={54} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      )

    case 'bar':
    case 'grouped_aggregate':
      return (
        <ChartFrame>
          <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data} margin={{ top: 20, right: 12, bottom: 30, left: 0 }} barCategoryGap="22%">
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#A78BFA" />
                  <stop offset="100%" stopColor="#6366F1" />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} angle={-30} textAnchor="end" interval="preserveStartEnd" height={62} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} formatter={(v: any) => [formatNumber(v, 4), chart.y_label ?? 'Value']} />
              <Bar dataKey="value" radius={[7, 7, 0, 0]} maxBarSize={58}>
                {data.map((_, i) => (
                  <Cell
                    key={i}
                    fill={PALETTE[i % PALETTE.length]}
                    fillOpacity={0.9}
                    stroke={PALETTE[i % PALETTE.length]}
                    strokeWidth={1}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      )

    case 'pie': {
      const total = data.reduce((sum: number, item: any) => sum + (Number(item.value) || 0), 0)

      return (
        <ChartFrame>
          <ResponsiveContainer width="100%" height={height}>
            <PieChart>
              <defs>
                {PALETTE.map((color, i) => (
                  <linearGradient key={i} id={`pieGradient${i}`} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor={color} />
                    <stop offset="100%" stopColor={color} stopOpacity={0.65} />
                  </linearGradient>
                ))}
              </defs>
              <Tooltip
                {...TOOLTIP}
                formatter={(v: any, n: any, p: any) => [
                  `${formatNumber(v)} (${formatNumber(p?.payload?.percentage ?? 0)}%)`,
                  n,
                ]}
              />
              <Legend {...LEGEND} verticalAlign="bottom" />
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                innerRadius="58%"
                outerRadius="82%"
                paddingAngle={3}
                stroke="rgba(15,23,42,0.8)"
                strokeWidth={2}
                cornerRadius={5}
              >
                {data.map((_, i) => (
                  <Cell
                    key={i}
                    fill={`url(#pieGradient${i % PALETTE.length})`}
                  />
                ))}
                <Label
                  value={formatNumber(total)}
                  position="center"
                  fill="#F8FAFC"
                  fontSize={22}
                  fontWeight={700}
                />
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </ChartFrame>
      )
    }

    case 'scatter':
      return (
        <ChartFrame>
          <ResponsiveContainer width="100%" height={height}>
            <ScatterChart margin={{ top: 18, right: 18, bottom: 25, left: 4 }}>
              <CartesianGrid {...GRID} vertical />
              <XAxis type="number" dataKey="x" name={chart.x} {...AXIS} domain={['auto', 'auto']} />
              <YAxis type="number" dataKey="y" name={chart.y} {...AXIS} domain={['auto', 'auto']} />
              <Tooltip
                {...TOOLTIP}
                formatter={(v: any) => formatNumber(v, 4)}
                cursor={{ strokeDasharray: '4 4', stroke: '#94A3B8' }}
              />
              <Scatter data={data} fill="#22D3EE" fillOpacity={0.8}>
                {data.map((_: any, i: number) => (
                  <Cell
                    key={i}
                    fill={PALETTE[i % PALETTE.length]}
                    fillOpacity={0.82}
                    stroke="#E0F2FE"
                    strokeOpacity={0.25}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartFrame>
      )

    case 'line':
      return (
        <ChartFrame>
          <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data} margin={{ top: 20, right: 16, bottom: 28, left: 0 }}>
              <defs>
                <linearGradient id="lineAreaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818CF8" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#818CF8" stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={24} height={48} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} formatter={(v: any) => [formatNumber(v, 4), chart.y_label ?? 'Value']} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="none"
                fill="url(#lineAreaGradient)"
                activeDot={false}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#818CF8"
                strokeWidth={3}
                dot={{ r: 3, fill: '#A5B4FC', stroke: '#312E81', strokeWidth: 2 }}
                activeDot={{ r: 7, fill: '#C4B5FD', stroke: '#6366F1', strokeWidth: 3 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartFrame>
      )

    case 'box': {
      const series = (chart as any).series ?? []
      if (!series.length) return <Empty />

      return (
        <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-900/50">
          <div className="overflow-auto">
            <table className="min-w-full">
              <thead>
                <tr className="bg-slate-800/80">
                  {['Group', 'Min', 'Q1', 'Median', 'Q3', 'Max', 'IQR', 'Outliers'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {series.map((s: any, i: number) => (
                  <tr key={i} className="border-t border-white/[0.06] transition-colors hover:bg-indigo-500/[0.07]">
                    <td className="px-4 py-3 text-sm font-semibold text-slate-100">{s.label}</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums text-slate-300">{formatNumber(s.min, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums text-slate-300">{formatNumber(s.q1, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs font-semibold tabular-nums text-indigo-300">{formatNumber(s.median, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums text-slate-300">{formatNumber(s.q3, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums text-slate-300">{formatNumber(s.max, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs tabular-nums text-cyan-300">{formatNumber(s.iqr, 4)}</td>
                    <td className="px-4 py-3 text-right text-xs font-semibold tabular-nums text-amber-300">{formatNumber(s.outlier_count ?? 0, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )
    }

    case 'correlation_heatmap': {
      const columns: string[] = (chart as any).columns ?? []
      const matrix: Record<string, Record<string, number>> = (chart as any).matrix ?? {}
      if (!columns.length) return <Empty />

      const colour = (v: number) => {
        const intensity = Math.min(Math.abs(v), 1)
        if (v > 0) return `rgba(59,130,246,${0.12 + intensity * 0.78})`
        if (v < 0) return `rgba(244,63,94,${0.12 + intensity * 0.78})`
        return 'rgba(148,163,184,0.08)'
      }

      return (
        <div className="overflow-auto rounded-2xl border border-white/[0.08] bg-slate-900/50 p-3">
          <div className="mb-3 flex flex-wrap items-center gap-4 text-[10px] text-slate-400">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-blue-500" /> Positive correlation
            </span>
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm bg-rose-500" /> Negative correlation
            </span>
          </div>
          <table className="min-w-full border-separate border-spacing-1 text-[11px]">
            <thead>
              <tr>
                <th className="sticky left-0 bg-slate-900 p-2" />
                {columns.map((c) => (
                  <th key={c} className="p-2 font-semibold text-slate-400" title={c}>
                    {c.slice(0, 12)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {columns.map((r) => (
                <tr key={r}>
                  <th className="sticky left-0 bg-slate-900 px-2 text-left font-semibold text-slate-300" title={r}>
                    {r.slice(0, 16)}
                  </th>
                  {columns.map((c) => {
                    const v = matrix[r]?.[c] ?? 0
                    return (
                      <td
                        key={c}
                        className="min-w-[48px] rounded-md p-2 text-center font-semibold tabular-nums text-white transition-transform hover:scale-105"
                        style={{ background: colour(v) }}
                        title={`${r} × ${c} = ${v.toFixed(3)}`}
                      >
                        {v.toFixed(2)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    default:
      return <Empty note={`Chart type "${chart.chart_type}" is not renderable in the browser.`} />
  }
}
