import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts'

import type { QuantHighlightBand, QuantHighlightColor } from '../types/quant'

type VisibleRect = {
  left: number
  right: number
  color: QuantHighlightColor
}

const HIGHLIGHT_FILL: Record<QuantHighlightColor, string> = {
  blue: 'rgba(37, 99, 235, 0.12)',
  red: 'rgba(239, 68, 68, 0.12)',
  purple: 'rgba(147, 51, 234, 0.14)',
}

class DateHighlightRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly primitive: DateHighlightPrimitive) {}

  draw(): void {}

  drawBackground(target: CanvasRenderingTarget2D): void {
    const rects = this.primitive.visibleRects()
    if (!rects.length) {
      return
    }

    target.useBitmapCoordinateSpace(({ context, bitmapSize, horizontalPixelRatio }) => {
      context.save()

      for (const rect of rects) {
        const left = Math.round(rect.left * horizontalPixelRatio)
        const right = Math.round(rect.right * horizontalPixelRatio)
        const width = Math.max(1, right - left)
        context.fillStyle = HIGHLIGHT_FILL[rect.color]
        context.fillRect(left, 0, width, bitmapSize.height)
      }

      context.restore()
    })
  }
}

class DateHighlightPaneView implements IPrimitivePaneView {
  constructor(private readonly primitive: DateHighlightPrimitive) {}

  zOrder(): PrimitivePaneViewZOrder {
    return 'bottom'
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.primitive.hasHighlights() ? this.primitive.renderer : null
  }
}

export class DateHighlightPrimitive implements ISeriesPrimitive<Time> {
  private chart: SeriesAttachedParameter<Time>['chart'] | null = null
  private series: SeriesAttachedParameter<Time>['series'] | null = null
  private requestUpdate: (() => void) | null = null
  private readonly view: DateHighlightPaneView
  readonly renderer: DateHighlightRenderer
  private highlights: QuantHighlightBand[] = []

  constructor(initialHighlights: QuantHighlightBand[] = []) {
    this.highlights = initialHighlights
    this.renderer = new DateHighlightRenderer(this)
    this.view = new DateHighlightPaneView(this)
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart
    this.series = param.series
    this.requestUpdate = param.requestUpdate
  }

  detached(): void {
    this.chart = null
    this.series = null
    this.requestUpdate = null
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.view]
  }

  setHighlights(highlights: QuantHighlightBand[]): void {
    this.highlights = highlights
    this.requestUpdate?.()
  }

  hasHighlights(): boolean {
    return this.highlights.length > 0
  }

  visibleRects(): VisibleRect[] {
    if (!this.chart || !this.series || !this.highlights.length) {
      return []
    }

    const highlightMap = new Map(this.highlights.map((item) => [item.tradeDate, item.color]))
    if (!highlightMap.size) {
      return []
    }

    const points = (this.series.data() as ReadonlyArray<{ time?: Time }>)
      .map((item) => item.time)
      .filter((time): time is Time => time !== undefined)
      .map((time) => ({
        time: String(time),
        x: this.chart?.timeScale().timeToCoordinate(time) ?? null,
      }))
      .filter((item) => item.x !== null)
      .map((item) => ({ time: item.time, x: Number(item.x) }))

    if (!points.length) {
      return []
    }

    const rects: VisibleRect[] = []

    for (let index = 0; index < points.length; index += 1) {
      const point = points[index]
      const color = highlightMap.get(point.time)
      if (!color) {
        continue
      }

      const previous = points[index - 1]
      const next = points[index + 1]
      const fallbackHalfWidth = 4
      const leftHalf =
        previous !== undefined ? Math.max(fallbackHalfWidth, (point.x - previous.x) / 2) : next ? Math.max(fallbackHalfWidth, (next.x - point.x) / 2) : fallbackHalfWidth
      const rightHalf =
        next !== undefined ? Math.max(fallbackHalfWidth, (next.x - point.x) / 2) : previous ? Math.max(fallbackHalfWidth, (point.x - previous.x) / 2) : fallbackHalfWidth

      rects.push({
        left: point.x - leftHalf,
        right: point.x + rightHalf,
        color,
      })
    }

    return mergeRects(rects)
  }
}

function mergeRects(rects: VisibleRect[]) {
  if (!rects.length) {
    return rects
  }

  const merged: VisibleRect[] = [rects[0]]

  for (let index = 1; index < rects.length; index += 1) {
    const current = rects[index]
    const previous = merged[merged.length - 1]

    if (previous.color === current.color && current.left <= previous.right + 1) {
      previous.right = Math.max(previous.right, current.right)
      continue
    }

    merged.push({ ...current })
  }

  return merged
}
