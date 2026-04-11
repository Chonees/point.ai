import { useEffect, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

/**
 * Shared offscreen renderer that generates thumbnails for GLB models.
 * Uses a single WebGL context for ALL thumbnails.
 * Renders 24 rotation frames per model for smooth hover animation.
 */

const THUMB_SIZE = 128
const FRAME_COUNT = 24  // full 360° in 24 steps = smooth rotation

const cache = new Map<string, string[]>()
const pending = new Map<string, Promise<string[]>>()

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let loader: GLTFLoader | null = null

function getRenderer() {
  if (!renderer) {
    const canvas = document.createElement('canvas')
    canvas.width = THUMB_SIZE
    canvas.height = THUMB_SIZE

    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    })
    renderer.setSize(THUMB_SIZE, THUMB_SIZE)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.2

    scene = new THREE.Scene()
    scene.background = new THREE.Color('#18181b')

    scene.add(new THREE.AmbientLight('#ffffff', 0.6))
    const dirLight = new THREE.DirectionalLight('#fff8ee', 2.0)
    dirLight.position.set(3, 4, 2)
    scene.add(dirLight)
    const fillLight = new THREE.DirectionalLight('#a0c0ff', 0.5)
    fillLight.position.set(-2, 2, -1)
    scene.add(fillLight)

    camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100)
    loader = new GLTFLoader()
  }
  return { renderer: renderer!, scene: scene!, camera: camera!, loader: loader! }
}

function renderThumbnails(url: string): Promise<string[]> {
  const { renderer: r, scene: s, camera: c, loader: l } = getRenderer()

  return new Promise((resolve, reject) => {
    l.load(
      url,
      (gltf) => {
        const toRemove = s.children.filter(
          (child) => child.type === 'Group' || child.type === 'Object3D' || child.type === 'Mesh',
        )
        for (const child of toRemove) s.remove(child)

        const model = gltf.scene

        const box = new THREE.Box3().setFromObject(model)
        const center = box.getCenter(new THREE.Vector3())
        const size = box.getSize(new THREE.Vector3())
        const maxDim = Math.max(size.x, size.y, size.z)
        const scale = maxDim > 0 ? 2 / maxDim : 1

        model.position.set(-center.x, -center.y, -center.z)
        model.scale.setScalar(scale)

        const wrapper = new THREE.Group()
        wrapper.add(model)
        s.add(wrapper)

        // Calculate camera distance to fit model at any rotation
        const scaledSize = size.clone().multiplyScalar(scale)
        const diagonal = Math.sqrt(
          scaledSize.x * scaledSize.x + scaledSize.y * scaledSize.y + scaledSize.z * scaledSize.z,
        )
        const fovRad = (c.fov * Math.PI) / 180
        const dist = (diagonal / 2) / Math.tan(fovRad / 2) * 1.35

        // Detect flat/floor models (height < 5% of max horizontal extent)
        const horizontalMax = Math.max(scaledSize.x, scaledSize.z)
        const isFlat = scaledSize.y < horizontalMax * 0.05

        if (isFlat) {
          // Rotate model so the flat face points at the camera
          model.rotation.x = -Math.PI / 2.8
          // Recompute after rotation
          const box2 = new THREE.Box3().setFromObject(wrapper)
          const center2 = box2.getCenter(new THREE.Vector3())
          model.position.sub(center2)
          c.position.set(0, 0, dist)
        } else {
          // Standard 3/4 view
          c.position.set(0, dist * 0.2, dist)
        }
        c.lookAt(0, 0, 0)

        // Render 24 frames for smooth 360° rotation
        const frames: string[] = []
        const step = (Math.PI * 2) / FRAME_COUNT
        for (let i = 0; i < FRAME_COUNT; i++) {
          wrapper.rotation.y = Math.PI / 5 + step * i
          r.render(s, c)
          frames.push(r.domElement.toDataURL('image/png'))
        }

        s.remove(wrapper)
        model.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) {
            const mesh = obj as THREE.Mesh
            mesh.geometry?.dispose()
            const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
            for (const mat of mats) mat?.dispose()
          }
        })

        resolve(frames)
      },
      undefined,
      (err) => reject(err),
    )
  })
}

async function getThumbnails(url: string): Promise<string[]> {
  const cached = cache.get(url)
  if (cached) return cached

  let promise = pending.get(url)
  if (!promise) {
    promise = renderThumbnails(url).then((frames) => {
      cache.set(url, frames)
      pending.delete(url)
      return frames
    }).catch((err) => {
      pending.delete(url)
      throw err
    })
    pending.set(url, promise)
  }

  return promise
}

/**
 * Hook: returns an array of 24 thumbnail data URLs (smooth rotation) for the given GLB.
 */
export function useThumbnail(glbPath: string): string[] | null {
  const [thumbs, setThumbs] = useState<string[] | null>(() => cache.get(glbPath) ?? null)

  useEffect(() => {
    let cancelled = false
    getThumbnails(glbPath).then((frames) => {
      if (!cancelled) setThumbs(frames)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [glbPath])

  return thumbs
}
