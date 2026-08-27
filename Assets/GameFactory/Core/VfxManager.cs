using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// One persistent, repositionable ParticleSystem shared by every burst
    /// effect (coin collect, gravity switch, ...). A particle parented to a
    /// pooled object (coin, obstacle) would stop rendering the instant
    /// GameObjectPool.Release() deactivates that object, so this stays in
    /// the scene root instead - callers just move it and Emit() a burst.
    /// </summary>
    [RequireComponent(typeof(ParticleSystem))]
    public class VfxManager : MonoBehaviour
    {
        public static VfxManager Instance { get; private set; }

        private ParticleSystem burstParticles;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }

            Instance = this;
            burstParticles = GetComponent<ParticleSystem>();
        }

        public void PlayBurst(Vector3 position, Color color, float size = 0.15f, int count = 10)
        {
            if (burstParticles == null) return;

            // Moved before Emit because the shape module emits from the
            // transform's current position, and simulationSpace is World -
            // so the burst stays where it was spawned.
            transform.position = position;

            ParticleSystem.EmitParams emitParams = new ParticleSystem.EmitParams
            {
                startColor = color,
                startSize = size
            };
            burstParticles.Emit(emitParams, count);
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }
    }
}
