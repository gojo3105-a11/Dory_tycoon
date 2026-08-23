using System;
using System.IO;
using System.Text;
using GameFactory.Core.Spec;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace GameFactory.Editor
{
    public enum AndroidBuildType { Apk, Aab }

    /// <summary>
    /// Builds ONE generated game as its own standalone Android package (only
    /// that game's scene is included in the build - this project can host
    /// many generated games over time, but each ships separately).
    ///
    /// Signing credentials are read from environment variables so nothing
    /// secret is ever committed; without them Unity's default debug signing
    /// is used, which installs fine for testing but is not accepted by the
    /// Play Store.
    ///
    /// CLI usage (see docs/BUILD.md):
    ///   Unity -batchmode -projectPath . -executeMethod
    ///     GameFactory.Editor.BuildAndroid.BuildFromCommandLine
    ///     -gameId factory_runner_001 -buildType apk -quit
    /// </summary>
    public static class BuildAndroid
    {
        [MenuItem("Game Factory/Build/Factory Runner (APK)")]
        private static void BuildFactoryRunnerApkMenuItem()
        {
            bool success = BuildAndReport("factory_runner_001", AndroidBuildType.Apk);
            EditorUtility.DisplayDialog("Game Factory Build", success ? "Build succeeded. See Builds/." : "Build failed. See Logs/unity-build.log.", "OK");
        }

        /// <summary>
        /// CLI entry point. Always exits Unity itself via CommandLineExit so
        /// the CI wrapper polling Logs/build.exitcode can tell the run is
        /// truly done - see scripts/ci/wait-for-unity.ps1.
        /// </summary>
        public static void BuildFromCommandLine()
        {
            string gameId = GetCommandLineArg("-gameId");
            string buildTypeArg = GetCommandLineArg("-buildType") ?? "apk";

            if (string.IsNullOrEmpty(gameId))
            {
                Debug.LogError("[BuildAndroid] Missing -gameId <id> command line argument.");
                CommandLineExit.Exit(1, "build");
                return;
            }

            if (!Enum.TryParse(buildTypeArg, true, out AndroidBuildType buildType))
            {
                Debug.LogError($"[BuildAndroid] Unknown -buildType '{buildTypeArg}' (expected apk or aab).");
                CommandLineExit.Exit(1, "build");
                return;
            }

            bool success = BuildAndReport(gameId, buildType);
            CommandLineExit.Exit(success ? 0 : 1, "build");
        }

        public static bool BuildAndReport(string gameId, AndroidBuildType buildType)
        {
            try
            {
                string outputPath = Build(gameId, buildType);
                Debug.Log($"[BuildAndroid] Build succeeded: {outputPath}");
                return true;
            }
            catch (Exception e)
            {
                Debug.LogError($"[BuildAndroid] Build failed for '{gameId}': {e}");
                WriteBuildLog(gameId, $"BUILD FAILED\n{e}");
                return false;
            }
        }

        public static string Build(string gameId, AndroidBuildType buildType)
        {
            string specPath = EditorPaths.ToAbsolutePath($"GameSpecs/{gameId}.json");
            GameSpec spec = GameSpecParser.LoadFromFile(specPath);

            ValidationResult validation = GameSpecValidator.Validate(spec);
            if (!validation.IsValid)
            {
                throw new GameSpecException(
                    $"GameSpec '{gameId}' failed validation:\n- " + string.Join("\n- ", validation.Errors));
            }

            string sceneAssetPath = $"Assets/GeneratedGames/{gameId}/Scenes/{gameId}.unity";
            if (!File.Exists(EditorPaths.ToAbsolutePath(sceneAssetPath)))
            {
                throw new InvalidOperationException(
                    $"No generated scene at {sceneAssetPath}. Run GameFactoryGenerator for '{gameId}' first.");
            }

            EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android, BuildTarget.Android);

            ConfigurePlayerSettings(spec);
            ConfigureSigning();

            EditorUserBuildSettings.buildAppBundle = buildType == AndroidBuildType.Aab;
            string extension = buildType == AndroidBuildType.Aab ? "aab" : "apk";
            string outputFolder = Path.Combine("Builds", gameId, buildType == AndroidBuildType.Aab ? "AAB" : "APK");
            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(outputFolder));
            string outputPath = Path.Combine(outputFolder, $"{gameId}.{extension}");

            var options = new BuildPlayerOptions
            {
                scenes = new[] { sceneAssetPath },
                locationPathName = outputPath,
                target = BuildTarget.Android,
                options = BuildOptions.None
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            WriteBuildLog(gameId, FormatReport(report));

            if (report.summary.result != BuildResult.Succeeded)
            {
                throw new InvalidOperationException(
                    $"Unity build did not succeed (result: {report.summary.result}, {report.summary.totalErrors} error(s)). See Logs/unity-build.log.");
            }

            return outputPath;
        }

        private static void ConfigurePlayerSettings(GameSpec spec)
        {
            PlayerSettings.productName = spec.game.title;
            PlayerSettings.applicationIdentifier = ResolveBundleId(spec.game.id);
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;

            if (string.IsNullOrEmpty(PlayerSettings.bundleVersion))
            {
                PlayerSettings.bundleVersion = "1.0.0";
            }

            if (PlayerSettings.Android.bundleVersionCode <= 0)
            {
                PlayerSettings.Android.bundleVersionCode = 1;
            }
        }

        /// <summary>
        /// Reuses the bundle id recorded from a previous generate/build of this
        /// game, if any, instead of re-deriving it - a published game's Android
        /// application id must never change underneath it.
        /// </summary>
        private static string ResolveBundleId(string gameId)
        {
            GeneratedGameManifest manifest = GeneratedGameManifest.Load(gameId) ?? new GeneratedGameManifest { gameId = gameId };
            if (!string.IsNullOrEmpty(manifest.bundleId))
            {
                return manifest.bundleId;
            }

            manifest.bundleId = BundleIdUtility.GetBundleId(gameId);
            manifest.Save(gameId);
            return manifest.bundleId;
        }

        private static void ConfigureSigning()
        {
            string keystorePath = Environment.GetEnvironmentVariable("ANDROID_KEYSTORE_PATH");
            if (string.IsNullOrEmpty(keystorePath))
            {
                Debug.LogWarning("[BuildAndroid] ANDROID_KEYSTORE_PATH not set; using Unity's default debug signing (not suitable for a Play Store release).");
                return;
            }

            PlayerSettings.Android.useCustomKeystore = true;
            PlayerSettings.Android.keystoreName = keystorePath;
            PlayerSettings.Android.keystorePass = Environment.GetEnvironmentVariable("ANDROID_KEYSTORE_PASS");
            PlayerSettings.Android.keyaliasName = Environment.GetEnvironmentVariable("ANDROID_KEYALIAS_NAME");
            PlayerSettings.Android.keyaliasPass = Environment.GetEnvironmentVariable("ANDROID_KEYALIAS_PASS");
        }

        private static string FormatReport(BuildReport report)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"Game Factory Android Build - {DateTime.UtcNow:o}");
            sb.AppendLine($"Result: {report.summary.result}");
            sb.AppendLine($"Errors: {report.summary.totalErrors}, Warnings: {report.summary.totalWarnings}");
            sb.AppendLine($"Size: {report.summary.totalSize} bytes, Time: {report.summary.totalTime}");
            sb.AppendLine();

            foreach (BuildStep step in report.steps)
            {
                foreach (BuildStepMessage message in step.messages)
                {
                    sb.AppendLine($"[{message.type}] ({step.name}) {message.content}");
                }
            }

            return sb.ToString();
        }

        private static void WriteBuildLog(string gameId, string content)
        {
            string logPath = Path.Combine(EditorPaths.ProjectRoot, "Logs", "unity-build.log");
            Directory.CreateDirectory(Path.GetDirectoryName(logPath));
            File.WriteAllText(logPath, $"[{gameId}]\n{content}");
        }

        private static string GetCommandLineArg(string name)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == name) return args[i + 1];
            }

            return null;
        }
    }
}
