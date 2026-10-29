import type { Scan } from './contracts.ts';
export function provenance(value: 'test' | 'recorded' | 'live' | 'mock' | undefined | null) {
  return value === 'test' ? 'TEST — synthetic evidence; not production approval'
    : value === 'mock' ? 'DEMO — synthetic scan; no backend authorization'
    : value === 'recorded' ? 'RECORDED — approval remains a backend decision'
    : value === 'live' ? 'LOCAL STATIC SCAN — code was parsed, not executed' : 'Evidence unavailable';
}
export function scanSummary(scan: Scan) {
  return { coverage: scan.scan_complete ? 'Scan complete within configured limits' : 'Partial scan — repository coverage is incomplete',
    graph: scan.graph_complete ? 'Graph analysis complete within supported static rules' : 'Partial graph — relationships may be missing',
    empty: scan.nodes.length === 0 ? (scan.scan_complete ? 'No supported LLM calls found.' : 'No supported calls observed in this partial scan; undiscovered calls may exist.') : null };
}
