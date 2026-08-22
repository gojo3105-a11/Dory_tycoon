using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>Single shared AudioSource for one-shot SFX. Kept intentionally minimal for MVP.</summary>
    [RequireComponent(typeof(AudioSource))]
    public class AudioManager : MonoBehaviour
    {
        public static AudioManager Instance { get; private set; }

        private AudioSource source;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }

            Instance = this;
            source = GetComponent<AudioSource>();
        }

        public void PlaySfx(AudioClip clip)
        {
            if (clip == null || source == null) return;
            source.PlayOneShot(clip);
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }
    }
}
