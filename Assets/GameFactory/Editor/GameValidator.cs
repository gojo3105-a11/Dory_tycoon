using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using GameFactory.Core;
using GameFactory.Core.Spec;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace GameFactory.Editor
{
    public class ValidationIssue
    {
        public string Severity; // "Error" or "Warning"
        public string Message;
    }

    /// <summary>
    /// Cross-file/cross-asset validation that GameSpecValidator (per-spec,
    /// structural) can't do on its own: duplicate game ids, bundle id
    /// collisions, and - for games that already have a generated scene -
    /// missing required objects/components and missing script references.
    /// A non-zero exit from ValidateFromCommandLine should block the build.
    /// </summary>
    public static class GameValidator
    {
        [MenuItem("Game Factory/Validate/All GameSpecs")]
        private static void ValidateAllMenuItem()
        {
            List<ValidationIssue> issues = ValidateAll();
            WriteLog(issues);

            int errorCount = issues.FindAll(i => i.Severity == "Error").Count;
            string message = errorCount > 0
                ? $"{errorCount} error(s), {issues.Count - errorCount} warning(s). See Logs/validation.log"
                : "All GameSpecs (and any generated scenes) are valid.";
            EditorUtility.DisplayDialog("Game Factory Validation", message, "OK");
        }

        /// <summary>
        /// CLI entry point driven by -executeMethod. Always exits Unity itself
        /// via CommandLineExit so the CI wrapper polling Logs/validate.exitcode
        /// can tell the run is truly done - see scripts/ci/wait-for-unity.ps1.
        /// </summary>
        public static void ValidateFromCommandLine()
        {
            List<ValidationIssue> issues = ValidateAll();
            WriteLog(issues);

            int errorCount = issues.FindAll(i => i.Severity == "Error").Count;
            if (errorCount > 0)
            {
                Debug.LogError($"[GameValidator] {errorCount} validation error(s). See Logs/validation.log");
                CommandLineExit.Exit(1, "validate");
                return;
            }

            Debug.Log($"[GameValidator] Validation passed ({issues.Count} warning(s)).");
            CommandLineExit.Exit(0, "validate");
        }

        public static List<ValidationIssue> ValidateAll()
        {
            var issues = new List<ValidationIssue>();
            string specsFolder = EditorPaths.ToAbsolutePath("GameSpecs");

            if (!Directory.Exists(specsFolder))
            {
                issues.Add(Error("GameSpecs/ folder not found."));
                return issues;
            }

            var idsSeen = new Dictionary<string, string>();
            var bundleIdsSeen = new Dictionary<string, string>();
            var validSpecs = new List<GameSpec>();

            foreach (string file in Directory.GetFiles(specsFolder, "*.json"))
            {
                string relativePath = "GameSpecs/" + Path.GetFileName(file);
                GameSpec spec;

                try
                {
                    spec = GameSpecParser.LoadFromFile(file);
                }
                catch (GameSpecException e)
                {
                    issues.Add(Error($"{relativePath}: {e.Message}"));
                    continue;
                }

                ValidationResult structural = GameSpecValidator.Validate(spec);
                foreach (string err in structural.Errors)
                {
                    issues.Add(Error($"{relativePath}: {err}"));
                }

                if (idsSeen.TryGetValue(spec.game.id, out string existingFile))
                {
                    issues.Add(Error($"Duplicate game.id '{spec.game.id}' in {relativePath} and {existingFile}."));
                }
                else
                {
                    idsSeen[spec.game.id] = relativePath;
                }

                string bundleId = BundleIdUtility.GetBundleId(spec.game.id);
                if (!BundleIdUtility.IsValidAndroidPackageName(bundleId))
                {
                    issues.Add(Error($"{relativePath}: derived bundle id '{bundleId}' is not a valid Android package name."));
                }
                else if (bundleIdsSeen.TryGetValue(bundleId, out string existingId))
                {
                    issues.Add(Error($"Bundle id '{bundleId}' collision between '{spec.game.id}' and '{existingId}'."));
                }
                else
                {
                    bundleIdsSeen[bundleId] = spec.game.id;
                }

                if (structural.IsValid)
                {
                    validSpecs.Add(spec);
                }
            }

            foreach (GameSpec spec in validSpecs)
            {
                ValidateGeneratedScene(spec, issues);
            }

            return issues;
        }

        private static void ValidateGeneratedScene(GameSpec spec, List<ValidationIssue> issues)
        {
            string sceneAssetPath = $"Assets/GeneratedGames/{spec.game.id}/Scenes/{spec.game.id}.unity";
            if (!File.Exists(EditorPaths.ToAbsolutePath(sceneAssetPath)))
            {
                issues.Add(Warning($"{spec.game.id}: no generated scene at {sceneAssetPath} yet (run GameFactoryGenerator first)."));
                return;
            }

            Scene scene;
            try
            {
                scene = EditorSceneManager.OpenScene(sceneAssetPath, OpenSceneMode.Additive);
            }
            catch (Exception e)
            {
                issues.Add(Error($"{spec.game.id}: failed to open scene {sceneAssetPath}: {e.Message}"));
                return;
            }

            try
            {
                bool hasGameManager = false;
                bool hasCamera = false;
                bool hasPlayer = false;
                bool hasCanvas = false;
                int missingScriptCount = 0;

                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
                    {
                        GameObject go = t.gameObject;

                        if (go.GetComponent<GameManager>() != null) hasGameManager = true;
                        if (go.GetComponent<Camera>() != null) hasCamera = true;
                        if (go.CompareTag("Player")) hasPlayer = true;
                        if (go.GetComponent<Canvas>() != null) hasCanvas = true;

                        foreach (Component c in go.GetComponents<Component>())
                        {
                            if (c == null) missingScriptCount++;
                        }
                    }
                }

                if (!hasGameManager) issues.Add(Error($"{spec.game.id}: scene is missing a GameManager."));
                if (!hasCamera) issues.Add(Error($"{spec.game.id}: scene is missing a Camera."));
                if (!hasPlayer) issues.Add(Error($"{spec.game.id}: scene is missing a Player-tagged object."));
                if (!hasCanvas) issues.Add(Error($"{spec.game.id}: scene is missing a UI Canvas."));
                if (missingScriptCount > 0)
                {
                    issues.Add(Error($"{spec.game.id}: scene has {missingScriptCount} missing script reference(s)."));
                }
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        private static ValidationIssue Error(string message) => new ValidationIssue { Severity = "Error", Message = message };

        private static ValidationIssue Warning(string message) => new ValidationIssue { Severity = "Warning", Message = message };

        private static void WriteLog(List<ValidationIssue> issues)
        {
            string logPath = Path.Combine(EditorPaths.ProjectRoot, "Logs", "validation.log");
            Directory.CreateDirectory(Path.GetDirectoryName(logPath));

            var sb = new StringBuilder();
            sb.AppendLine($"Game Factory Validation - {DateTime.UtcNow:o}");
            sb.AppendLine($"Total issues: {issues.Count}");
            foreach (ValidationIssue issue in issues)
            {
                sb.AppendLine($"[{issue.Severity}] {issue.Message}");
            }

            File.WriteAllText(logPath, sb.ToString());
        }
    }
}
