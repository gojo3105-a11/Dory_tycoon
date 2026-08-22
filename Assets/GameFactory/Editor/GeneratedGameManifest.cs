using System;
using System.IO;
using UnityEngine;

namespace GameFactory.Editor
{
    /// <summary>
    /// Metadata about one generated game, persisted at GeneratedGames/&lt;id&gt;.json
    /// (repo root, outside Assets/ - it's a build log, not a Unity asset).
    /// Both GameFactoryGenerator and BuildAndroid read/write this so a game's
    /// bundleId, once assigned, survives regeneration and is never silently
    /// re-derived differently on a later build.
    /// </summary>
    [Serializable]
    public class GeneratedGameManifest
    {
        public string gameId;
        public string title;
        public string genre;
        public string generatedAtUtc;
        public string scenePath;
        public string[] prefabPaths = new string[0];
        public string bundleId;

        public static GeneratedGameManifest Load(string gameId)
        {
            string path = PathFor(gameId);
            return File.Exists(path) ? JsonUtility.FromJson<GeneratedGameManifest>(File.ReadAllText(path)) : null;
        }

        public void Save(string gameId)
        {
            string path = PathFor(gameId);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, JsonUtility.ToJson(this, true));
        }

        private static string PathFor(string gameId)
        {
            return Path.Combine(EditorPaths.ProjectRoot, "GeneratedGames", $"{gameId}.json");
        }
    }
}
