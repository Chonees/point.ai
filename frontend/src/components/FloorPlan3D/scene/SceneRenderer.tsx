import { useEffect } from 'react'
import { useThree } from '@react-three/fiber'
import { Bloom, EffectComposer, SSAO, ToneMapping } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import * as THREE from 'three'

const BACKGROUND_COLOR = '#dbeaf7'

export function SceneEffects() {
  const { gl } = useThree()

  return (
    <EffectComposer
      depthBuffer
      enableNormalPass
      multisampling={gl.capabilities.isWebGL2 ? 4 : 0}
      resolutionScale={0.65}
    >
      <SSAO
        samples={21}
        rings={4}
        radius={0.045}
        intensity={4.5}
        luminanceInfluence={0.72}
        bias={0.025}
      />
      <Bloom
        mipmapBlur
        intensity={0.035}
        luminanceThreshold={1.18}
        luminanceSmoothing={0.05}
        radius={0.42}
      />
      <ToneMapping
        mode={ToneMappingMode.ACES_FILMIC}
        whitePoint={5.5}
        middleGrey={0.72}
        minLuminance={0.02}
        averageLuminance={0.9}
        resolution={256}
      />
    </EffectComposer>
  )
}

export function SceneRenderer({ camDist }: { camDist: number }) {
  const { gl, scene } = useThree()

  useEffect(() => {
    const previousBackground = scene.background
    const previousFog = scene.fog

    scene.background = new THREE.Color(BACKGROUND_COLOR)
    scene.fog = new THREE.Fog(BACKGROUND_COLOR, camDist * 3.5, camDist * 11)
    gl.outputColorSpace = THREE.SRGBColorSpace
    gl.shadowMap.enabled = true
    gl.shadowMap.type = THREE.PCFSoftShadowMap

    return () => {
      scene.background = previousBackground
      scene.fog = previousFog
    }
  }, [camDist, gl, scene])

  return null
}
