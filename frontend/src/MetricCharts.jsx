import { METHODS } from './api'

export function BarChart({ title, series, value, format, minimum = 0.05 }) {
  const names = [...new Set(series.flatMap(s => Object.keys(s.methods ?? {})))]
  const values = series.flatMap(s => names.map(name => value(s.methods?.[name])).filter(v => v != null))
  const highest = Math.max(minimum, ...values)
  const step = 10 ** Math.floor(Math.log10(highest))
  const maximum = Math.ceil(highest / step) * step
  return <figure className="metric-chart">
    <figcaption>{title}</figcaption>
    <div className="chart-legend">{series.map((s, i) => <span key={s.label}><i style={{ background: i ? '#b17835' : '#36735a' }} />{s.label}</span>)}</div>
    <div className="chart-axis"><span>0</span><span>{format(maximum)}</span></div>
    {names.map(name => <div className="chart-row" key={name}>
      <strong>{METHODS[name] ?? name}</strong>
      {series.map((s, i) => {
        const number = value(s.methods?.[name])
        return <div className="bar-row" key={s.label} title={`${s.label}: ${number == null ? 'Not measured' : format(number)}`}>
          <span className="bar-track" aria-hidden="true"><span style={{ width: `${number == null ? 0 : number / maximum * 100}%`, background: i ? '#b17835' : '#36735a' }} /></span>
          <span className="bar-value">{number == null ? 'N/A' : format(number)}</span>
        </div>
      })}
    </div>)}
  </figure>
}

export default function MetricCharts({ series, coveredOnly = false }) {
  const metrics = m => coveredOnly ? m?.covered_only : m
  return <div className="metric-charts">
    <BarChart title="Success@5 · higher is better" series={series} value={m => metrics(m)?.success_at_5} format={v => `${(v * 100).toFixed(1)}%`} />
    <BarChart title="MRR@10 · higher is better" series={series} value={m => metrics(m)?.mrr_at_10} format={v => v.toFixed(3)} />
    <BarChart title="Mean retrieval latency · lower is better" series={series} value={m => m?.latency_ms.mean} format={v => `${v.toFixed(1)} ms`} minimum={1} />
  </div>
}
