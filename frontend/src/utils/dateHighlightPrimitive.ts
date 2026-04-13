import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts'

import type { QuantHighlightBand, QuantHighlightColor, QuantHighlightVariant } from '../types/quant'

type VisibleRect = {
  left: number
  right: number
  color: QuantHighlightColor
  variant: QuantHighlightVariant
}

const HIGHLIGHT_FILL: Record<QuantHighlightColor, string> = {
  blue: 'rgba(29, 78, 216, 0.24)',
  red: 'rgba(220, 38, 38, 0.24)',
  purple: 'rgba(126, 34, 206, 0.26)',
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
        if (rect.variant === 'striped') {
          const stripeGap = Math.max(6, Math.round(10 * horizontalPixelRatio))
          const stripeWidth = Math.max(2, Math.round(4 * horizontalPixelRatio))
          context.save()
          context.beginPath()
          context.rect(left, 0, width, bitmapSize.height)
          context.clip()
          context.strokeStyle = 'rgba(255, 255, 255, 0.38)'
          context.lineWidth = stripeWidth
          for (let start = left - bitmapSize.height; start < right + bitmapSize.height; start += stripeGap) {
            context.beginPath()
            context.moveTo(start, bitmapSize.height)
            context.lineTo(start + bitmapSize.height, 0)
            context.stroke()
          }
          context.restore()
        }
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

    const highlightMap = new Map(this.highlights.map((item) => [item.tradeDate, item]))
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
      const band = highlightMap.get(point.time)
      if (!band) {
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
        color: band.color,
        variant: band.variant ?? 'solid',
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

    if (previous.color === current.color && previous.variant === current.variant && current.left <= previous.right + 1) {
      previous.right = Math.max(previous.right, current.right)
      continue
    }

    merged.push({ ...current })
  }

  return merged
}
