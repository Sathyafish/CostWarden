import { compactMoney, money, shortDate, splitLinks, statusLabel, timeAgo } from './format'

describe('format', () => {
  it('formats money', () => {
    expect(money(1234.5)).toBe('$1,234.50')
    expect(money(1234.5, 0)).toBe('$1,235')
  })
  it('compacts large amounts', () => {
    expect(compactMoney(850)).toBe('$850')
    expect(compactMoney(12500)).toBe('$12.5K')
    expect(compactMoney(2_400_000)).toBe('$2.4M')
  })
  it('formats dates in UTC', () => {
    expect(shortDate('2026-10-05T00:00:00Z')).toBe('Oct 5')
    expect(shortDate('garbage')).toBe('garbage')
  })
  it('describes age', () => {
    const now = new Date('2026-10-24T12:00:00Z')
    expect(timeAgo('2026-10-24T01:00:00Z', now)).toBe('today')
    expect(timeAgo('2026-10-23T00:00:00Z', now)).toBe('1 day ago')
    expect(timeAgo('2026-10-14T00:00:00Z', now)).toBe('10 days ago')
  })
  it('splits links and trims trailing punctuation', () => {
    expect(splitLinks('See https://x.io/pr/1. Done')).toEqual([
      { text: 'See ' },
      { text: 'https://x.io/pr/1', href: 'https://x.io/pr/1' },
      { text: '. Done' },
    ])
    expect(splitLinks('no links')).toEqual([{ text: 'no links' }])
  })
  it('labels statuses', () => {
    expect(statusLabel('pr_open')).toBe('Pr open')
  })
})
