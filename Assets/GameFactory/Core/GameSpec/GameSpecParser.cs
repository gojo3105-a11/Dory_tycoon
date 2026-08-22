using System;
using System.IO;
using UnityEngine;

namespace GameFactory.Core.Spec
{
    /// <summary>
    /// Thrown when a GameSpec JSON file cannot be found, read, or parsed.
    /// Always carries the offending path/id so Claude Code (or a human) can
    /// jump straight to the broken file.
    /// </summary>
    public class GameSpecException : Exception
    {
        public GameSpecException(string message) : base(message) { }
        public GameSpecException(string message, Exception inner) : base(message, inner) { }
    }

    /// <summary>
    /// Reads GameSpec JSON from disk (editor/CI tooling) or from Resources
    /// (runtime). Parsing is intentionally strict: any structural problem
    /// throws GameSpecException with the source path instead of silently
    /// returning a half-populated spec.
    /// </summary>
    public static class GameSpecParser
    {
        public const string ResourcesFolder = "GameSpecs";

        public static GameSpec LoadFromJson(string json, string sourceLabel = "<inline json>")
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                throw new GameSpecException($"GameSpec source '{sourceLabel}' is empty.");
            }

            GameSpec spec;
            try
            {
                spec = JsonUtility.FromJson<GameSpec>(json);
            }
            catch (Exception e)
            {
                throw new GameSpecException($"Failed to parse GameSpec JSON from '{sourceLabel}': {e.Message}", e);
            }

            if (spec == null || spec.game == null || string.IsNullOrEmpty(spec.game.id))
            {
                throw new GameSpecException(
                    $"GameSpec source '{sourceLabel}' parsed but 'game.id' is missing. " +
                    "Check the JSON structure against docs/GAME_SPEC.md.");
            }

            return spec;
        }

        /// <summary>Loads a GameSpec from an absolute or project-relative file path (editor/CI use).</summary>
        public static GameSpec LoadFromFile(string filePath)
        {
            if (!File.Exists(filePath))
            {
                throw new GameSpecException($"GameSpec file not found: {filePath}");
            }

            string json;
            try
            {
                json = File.ReadAllText(filePath);
            }
            catch (Exception e)
            {
                throw new GameSpecException($"Failed to read GameSpec file '{filePath}': {e.Message}", e);
            }

            return LoadFromJson(json, filePath);
        }

        /// <summary>
        /// Loads a GameSpec baked into Resources/GameSpecs/&lt;id&gt;.json (runtime use).
        /// The generator copies the authored spec here as part of game generation.
        /// </summary>
        public static GameSpec LoadFromResources(string gameId)
        {
            string resourcePath = $"{ResourcesFolder}/{gameId}";
            TextAsset asset = Resources.Load<TextAsset>(resourcePath);
            if (asset == null)
            {
                throw new GameSpecException(
                    $"GameSpec resource not found at 'Resources/{resourcePath}.json'. " +
                    "Has GameFactoryGenerator been run for this game id?");
            }

            return LoadFromJson(asset.text, resourcePath);
        }

        public static string ToJson(GameSpec spec, bool prettyPrint = true)
        {
            if (spec == null)
            {
                throw new ArgumentNullException(nameof(spec));
            }

            return JsonUtility.ToJson(spec, prettyPrint);
        }
    }
}
