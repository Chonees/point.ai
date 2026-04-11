import { useRef, useEffect } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import { PointerLockControls } from '@react-three/drei'
import * as THREE from 'three'

const MOVE_SPEED = 80
const EYE_HEIGHT = 60 // ~5 feet

export function WalkControls({ center }: { center: { x: number; z: number } }) {
  const { camera, gl } = useThree()
  const controlsRef = useRef<any>(null)
  const keys = useRef({ w: false, a: false, s: false, d: false })
  const velocity = useRef(new THREE.Vector3())
  const direction = useRef(new THREE.Vector3())

  // Set initial position at eye height
  useEffect(() => {
    camera.position.set(center.x, EYE_HEIGHT, center.z)
    camera.lookAt(center.x + 50, EYE_HEIGHT, center.z)
  }, [camera, center])

  // Keyboard listeners
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase()
      if (k in keys.current) (keys.current as any)[k] = true
    }
    const onUp = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase()
      if (k in keys.current) (keys.current as any)[k] = false
    }
    document.addEventListener('keydown', onDown)
    document.addEventListener('keyup', onUp)
    return () => {
      document.removeEventListener('keydown', onDown)
      document.removeEventListener('keyup', onUp)
    }
  }, [])

  // Lock on click
  useEffect(() => {
    const onClick = () => controlsRef.current?.lock()
    gl.domElement.addEventListener('click', onClick)
    return () => gl.domElement.removeEventListener('click', onClick)
  }, [gl])

  // Movement loop
  useFrame((_, delta) => {
    if (!controlsRef.current?.isLocked) return

    const speed = MOVE_SPEED * delta
    direction.current.set(0, 0, 0)

    if (keys.current.w) direction.current.z -= 1
    if (keys.current.s) direction.current.z += 1
    if (keys.current.a) direction.current.x -= 1
    if (keys.current.d) direction.current.x += 1

    if (direction.current.lengthSq() > 0) {
      direction.current.normalize()
      // Move relative to camera facing direction (but stay on ground)
      const forward = new THREE.Vector3()
      camera.getWorldDirection(forward)
      forward.y = 0
      forward.normalize()
      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize()

      velocity.current
        .copy(forward).multiplyScalar(-direction.current.z * speed)
        .add(right.clone().multiplyScalar(direction.current.x * speed))

      camera.position.add(velocity.current)
    }

    // Lock Y to eye height
    camera.position.y = EYE_HEIGHT
  })

  return <PointerLockControls ref={controlsRef} />
}
