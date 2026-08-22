using System;
using UnityEngine;

namespace GameFactory.Modules.GravitySwitch
{
    /// <summary>
    /// Flips the engine's global 2D gravity for the "gravity reverses in
    /// certain zones" gimmick. Only meaningful when the player is the only
    /// gravity-affected Rigidbody2D in the scene, which holds for the Runner
    /// genre's MVP scope.
    /// </summary>
    public static class GravitySwitchController
    {
        public static event Action<bool> GravityInvertedChanged;
        public static bool IsInverted { get; private set; }

        private static float baseGravityMagnitude;
        private static bool initialized;

        private static void EnsureInitialized()
        {
            if (initialized) return;

            baseGravityMagnitude = Mathf.Abs(Physics2D.gravity.y);
            if (baseGravityMagnitude <= 0f) baseGravityMagnitude = 9.81f;
            initialized = true;
        }

        public static void SetInverted(bool inverted)
        {
            EnsureInitialized();
            if (IsInverted == inverted) return;

            IsInverted = inverted;
            Physics2D.gravity = new Vector2(0f, inverted ? baseGravityMagnitude : -baseGravityMagnitude);
            GravityInvertedChanged?.Invoke(inverted);
        }

        /// <summary>Called on scene (re)start so a mid-flip death/restart never carries stale gravity over.</summary>
        public static void ResetToDefault()
        {
            EnsureInitialized();
            IsInverted = false;
            Physics2D.gravity = new Vector2(0f, -baseGravityMagnitude);
        }
    }
}
