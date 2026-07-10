import type { EdgePair } from './layout'
import { initialLayout, forceLayout, dagreLayout, gridLayout, circleLayout } from './layout'

const ids = (n: number) => Array.from({ length: n }, (_, i) => `h${i}`)

function allFinite(pos: Map<string, { x: number; y: number }>): boolean {
  for (const p of pos.values()) {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) return false
  }
  return true
}

describe('gridLayout', () => {
  it('places nodes on a row-major grid with sqrt columns (exact coords)', () => {
    const pos = gridLayout(['a', 'b', 'c', 'd']) // cols = ceil(sqrt(4)) = 2
    expect(pos.get('a')).toEqual({ x: 60, y: 60 })
    expect(pos.get('b')).toEqual({ x: 200, y: 60 })
    expect(pos.get('c')).toEqual({ x: 60, y: 200 })
    expect(pos.get('d')).toEqual({ x: 200, y: 200 })
  })

  it('returns an empty map for no nodes', () => {
    expect(gridLayout([]).size).toBe(0)
  })
})

describe('circleLayout', () => {
  it('places every node at a finite coordinate around a circle', () => {
    const pos = circleLayout(ids(8))
    expect(pos.size).toBe(8)
    expect(allFinite(pos)).toBe(true)
  })

  it('starts the first node at the top of the circle', () => {
    const pos = circleLayout(['only']) // r=140, angle=-π/2 → cos=0, sin=-1
    expect(pos.get('only')).toEqual({ x: 196, y: 56 })
  })
})

describe('forceLayout', () => {
  it('returns a finite position for every node', () => {
    const edges: EdgePair[] = [{ source: 'h0', target: 'h1' }, { source: 'h1', target: 'h2' }]
    const pos = forceLayout(ids(3), edges, 200)
    expect(pos.size).toBe(3)
    expect(allFinite(pos)).toBe(true)
  })

  it('drops edges whose endpoints are not in the node set without throwing', () => {
    const pos = forceLayout(['a', 'b'], [{ source: 'a', target: 'ghost' }], 200)
    expect(pos.size).toBe(2)
    expect(allFinite(pos)).toBe(true)
  })

  it('is deterministic across runs for the same input', () => {
    const edges: EdgePair[] = [{ source: 'h0', target: 'h1' }]
    expect(forceLayout(ids(2), edges, 200)).toEqual(forceLayout(ids(2), edges, 200))
  })
})

describe('dagreLayout', () => {
  it('returns a finite position for every node in a small DAG', () => {
    const edges: EdgePair[] = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }]
    const pos = dagreLayout(['a', 'b', 'c'], edges)
    expect(pos.size).toBe(3)
    expect(allFinite(pos)).toBe(true)
  })

  it('ignores edges referencing unknown nodes', () => {
    const pos = dagreLayout(['a', 'b'], [{ source: 'a', target: 'ghost' }])
    expect(pos.size).toBe(2)
    expect(allFinite(pos)).toBe(true)
  })
})

describe('initialLayout', () => {
  it('returns an empty map when there are no nodes, whatever the layout', () => {
    expect(initialLayout('grid', [], []).size).toBe(0)
    expect(initialLayout('cola', [], []).size).toBe(0)
  })

  it('dispatches grid/circle/breadthfirst to their algorithms', () => {
    expect(initialLayout('grid', ['a', 'b'], [])).toEqual(gridLayout(['a', 'b']))
    expect(initialLayout('circle', ['a', 'b'], [])).toEqual(circleLayout(['a', 'b']))
    expect(initialLayout('breadthfirst', ['a', 'b'], [{ source: 'a', target: 'b' }]))
      .toEqual(dagreLayout(['a', 'b'], [{ source: 'a', target: 'b' }]))
  })

  it('dispatches cola/cose-bilkent to a force layout (finite positions for all)', () => {
    const pos = initialLayout('cola', ids(4), [{ source: 'h0', target: 'h1' }])
    expect(pos.size).toBe(4)
    expect(allFinite(pos)).toBe(true)
  })
})
