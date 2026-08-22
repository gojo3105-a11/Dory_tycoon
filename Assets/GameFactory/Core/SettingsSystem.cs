using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>Global (not per-game) player preferences shared across every generated game.</summary>
    public static class SettingsSystem
    {
        private const string SoundEnabledKey = "settings.sound_enabled";

        public static bool SoundEnabled
        {
            get => PlayerPrefs.GetInt(SoundEnabledKey, 1) == 1;
            set
            {
                PlayerPrefs.SetInt(SoundEnabledKey, value ? 1 : 0);
                PlayerPrefs.Save();
            }
        }
    }
}
