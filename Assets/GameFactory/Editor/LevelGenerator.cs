using GameFactory.Core.Spec;
using GameFactory.Gameplay.Runner;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Wires up procedural level content that depends on GameSpec mechanics
    /// (currently: GravitySwitch zones). Ground/obstacle/coin placement is
    /// already infinite-procedural at runtime via their own spawners; this
    /// class only decides whether/how the *gimmick* layer participates.
    /// </summary>
    public static class LevelGenerator
    {
        public static void ConfigureRunnerLevel(GameSpec spec, Transform player, GameObject gravityZonePrefab)
        {
            if (!spec.mechanics.gravitySwitch)
            {
                return;
            }

            if (gravityZonePrefab == null)
            {
                Debug.LogError("[LevelGenerator] mechanics.gravitySwitch is true but no GravityZone prefab was generated.");
                return;
            }

            GameObject spawnerGO = new GameObject("GravityZoneSpawner");
            GravityZoneSpawner spawner = spawnerGO.AddComponent<GravityZoneSpawner>();
            spawner.SetReferences(gravityZonePrefab, player, 0f);
            spawner.Configure(spec.level.length);
        }
    }
}
