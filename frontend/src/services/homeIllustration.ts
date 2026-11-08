/**
 * Home screen illustration fixture.
 * Explicit illustrative data for the first-run example card.
 * Never an API fallback or backend authorization.
 */

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
  summarySentence: string;
  footerNote: string;
}

export const homeIllustrationFixture: HomeIllustration = {
  isIllustration: true,
  mandatoryLabel: 'Example, not your data',
  title: 'What a result looks like',
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
  summarySentence: 'Two of three calls can move to a cheaper model. The third stays where it is.',
  footerNote: 'Models: NVIDIA Nemotron, served by Nebius Token Factory.',
};

