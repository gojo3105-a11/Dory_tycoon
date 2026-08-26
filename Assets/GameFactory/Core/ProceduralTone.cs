using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Generates short sine-tone placeholder SFX at runtime via AudioClip.Create.
    /// The project has no licensed sound assets yet (see
    /// Documentation/CURRENT_GAME_ANALYSIS.md TASK-002) - callers should treat
    /// clips from here as temporary and swap in real audio later.
    /// </summary>
    public static class ProceduralTone
    {
        private const int SampleRate = 44100;

        /// <summary>A single sine tone with a short fade-in/out so it doesn't click at the edges.</summary>
        public static AudioClip Sine(string name, float frequencyHz, float durationSeconds, float volume = 0.35f)
        {
            int sampleCount = Mathf.Max(1, Mathf.RoundToInt(SampleRate * durationSeconds));
            int fadeSamples = Mathf.Clamp(sampleCount / 4, 1, SampleRate / 50);
            float[] samples = new float[sampleCount];

            for (int i = 0; i < sampleCount; i++)
            {
                float t = (float)i / SampleRate;
                float envelope = 1f;
                if (i < fadeSamples) envelope = (float)i / fadeSamples;
                else if (i > sampleCount - fadeSamples) envelope = (float)(sampleCount - i) / fadeSamples;

                samples[i] = Mathf.Sin(2f * Mathf.PI * frequencyHz * t) * volume * envelope;
            }

            AudioClip clip = AudioClip.Create(name, sampleCount, 1, SampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }
    }
}
