import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OpeningsReviewCanvas } from './OpeningsReviewCanvas'

function stubImageMetrics(image: HTMLImageElement) {
  Object.defineProperty(image, 'naturalWidth', {
    configurable: true,
    value: 200,
  })
  Object.defineProperty(image, 'naturalHeight', {
    configurable: true,
    value: 120,
  })
  image.getBoundingClientRect = () => ({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 200,
    bottom: 120,
    width: 200,
    height: 120,
    toJSON: () => ({}),
  }) as DOMRect
}

describe('OpeningsReviewCanvas', () => {
  it('selects the opening first and only moves from the move handle', () => {
    const onChange = vi.fn()
    const annotations = [
      { type: 'door' as const, x1: 50, y1: 20, x2: 50, y2: 70 },
    ]

    const { container } = render(
      <OpeningsReviewCanvas
        imageSrc="data:image/png;base64,AAAA"
        annotations={annotations}
        onChange={onChange}
      />,
    )

    const image = screen.getByAltText('Openings review source') as HTMLImageElement
    stubImageMetrics(image)
    fireEvent.load(image)

    const hitArea = container.querySelector('svg line')
    expect(hitArea).not.toBeNull()

    fireEvent.pointerDown(hitArea!, { clientX: 50, clientY: 30 })
    fireEvent.pointerUp(hitArea!, { clientX: 50, clientY: 30 })

    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByTestId('opening-move-handle')).toBeInTheDocument()
    expect(screen.getByTestId('opening-move-handle')).toHaveAttribute('stroke', '#38bdf8')
    expect(screen.getByTestId('opening-move-glyph')).toHaveAttribute('fill', '#38bdf8')
  })

  it('shows blue swing targets and lets the user choose direction by clicking them', () => {
    const onChange = vi.fn()
    const annotations = [
      { type: 'door' as const, x1: 50, y1: 20, x2: 50, y2: 70 },
    ]

    const { container } = render(
      <OpeningsReviewCanvas
        imageSrc="data:image/png;base64,AAAA"
        annotations={annotations}
        onChange={onChange}
      />,
    )

    const image = screen.getByAltText('Openings review source') as HTMLImageElement
    stubImageMetrics(image)
    fireEvent.load(image)

    const hitArea = container.querySelector('svg line')
    expect(hitArea).not.toBeNull()

    fireEvent.pointerDown(hitArea!, { clientX: 50, clientY: 30 })
    fireEvent.pointerUp(hitArea!, { clientX: 50, clientY: 30 })

    expect(container.querySelector('line[stroke="#38bdf8"]')).not.toBeNull()

    const leftTarget = screen.getByTestId('opening-swing-target-left')
    expect(leftTarget).toHaveAttribute('stroke', '#38bdf8')
    expect(leftTarget).toHaveAttribute('fill', 'rgba(56,189,248,0.18)')

    fireEvent.pointerDown(leftTarget)

    expect(onChange).toHaveBeenCalledWith([
      { type: 'door', x1: 50, y1: 20, x2: 50, y2: 70, swing: 'left' },
    ])
  })

  it('moves the opening only when dragging the move handle', () => {
    const onChange = vi.fn()
    const annotations = [
      { type: 'door' as const, x1: 50, y1: 20, x2: 50, y2: 70, swing: 'left' },
    ]

    const { container } = render(
      <OpeningsReviewCanvas
        imageSrc="data:image/png;base64,AAAA"
        annotations={annotations}
        onChange={onChange}
      />,
    )

    const image = screen.getByAltText('Openings review source') as HTMLImageElement
    stubImageMetrics(image)
    fireEvent.load(image)

    const hitArea = container.querySelector('svg line')
    expect(hitArea).not.toBeNull()

    fireEvent.pointerDown(hitArea!, { clientX: 50, clientY: 30 })
    fireEvent.pointerUp(hitArea!, { clientX: 50, clientY: 30 })

    fireEvent.pointerDown(screen.getByTestId('opening-move-handle'), { clientX: 50, clientY: 45 })
    fireEvent.pointerMove(window, { clientX: 60, clientY: 55 })

    expect(onChange).toHaveBeenCalledWith([
      { type: 'door', x1: 60, y1: 30, x2: 60, y2: 80, swing: 'left' },
    ])
  })
})
