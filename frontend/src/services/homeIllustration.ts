/**
 * Home screen illustration fixture.
 * Explicit illustrative data for the first-run example card and route board.
 * Never an API fallback or backend authorization.
 */
import type { BoardCallItem } from '../components/board/TierBoard.tsx';

export interface IllustrationCall {
  name: string;
  chip: { text: string; kind: 'gain' | 'neutral' };
  now?: { label: string; barWidthPx: number; cost: string };
  recommended?: { label: string; barWidthPx: number; cost: string };
  note?: string;
}

export interface HomeIllustration {
  isIllustration: true;
  mandatoryLabel: string;
  title: string;
  calls: readonly IllustrationCall[];
  boardCalls: readonly BoardCallItem[];
  summarySentence: string;
  footerNote: string;
}

export const homeIllustrationFixture: HomeIllustration = {
  isIllustration: true,
  mandatoryLabel: 'Example, not your data',
  title: 'Where each call runs',
  calls: [
    {
      name: 'Triage intent',
      chip: { text: 'Ultra to Nano', kind: 'gain' },
      now: { label: 'Now', barWidthPx: 160, cost: '$0.000459' },
      recommended: { label: 'Recommended', barWidthPx: 11, cost: '$0.000030' },
    },
    {
      name: 'Extract context',
      chip: { text: 'Ultra to Lightning', kind: 'gain' },
      now: { label: 'Now', barWidthPx: 160, cost: '$0.000612' },
      recommended: { label: 'Recommended', barWidthPx: 14, cost: '$0.000052' },
    },
    {
      name: 'Draft reply',
      chip: { text: 'Stays on Ultra', kind: 'neutral' },
      note: 'No cheaper model passed every check, so nothing changes.',
    },
  ],
  boardCalls: [
    {
      id: 'call_triage',
      name: 'Triage intent',
      location: 'support_agent.py:14',
      currentModel: 'nvidia/Ultra',
      illustrationPick: 'nvidia/Nano',
      illustrationSavings: '93%',
      illustrationStations: {
        'nvidia/Nano': 'passed',
        'nvidia/Lightning': 'passed',
        'nvidia/Flash': 'passed',
        'nvidia/Ultra': 'passed',
      },
    },
    {
      id: 'call_extract',
      name: 'Extract context',
      location: 'support_agent.py:28',
      currentModel: 'nvidia/Ultra',
      illustrationPick: 'nvidia/Lightning',
      illustrationSavings: '87%',
      illustrationStations: {
        'nvidia/Nano': 'failed',
        'nvidia/Lightning': 'passed',
        'nvidia/Flash': 'passed',
        'nvidia/Ultra': 'passed',
      },
    },
    {
      id: 'call_reply',
      name: 'Draft reply',
      location: 'support_agent.py:42',
      currentModel: 'nvidia/Ultra',
      illustrationPick: 'nvidia/Ultra',
      illustrationSavings: null,
      illustrationStations: {
        'nvidia/Nano': 'failed',
        'nvidia/Lightning': 'failed',
        'nvidia/Flash': 'failed',
        'nvidia/Ultra': 'passed',
      },
    },
  ],
  summarySentence: 'Two of three calls can move to a cheaper model. The third stays where it is.',
  footerNote: 'Models: NVIDIA Nemotron, served by Nebius Token Factory.',
};
