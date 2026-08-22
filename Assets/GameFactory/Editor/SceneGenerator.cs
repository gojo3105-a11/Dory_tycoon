using System.IO;
using GameFactory.Core;
using GameFactory.Core.Spec;
using GameFactory.Gameplay.Runner;
using GameFactory.UI;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace GameFactory.Editor
{
    /// <summary>
    /// Assembles and saves the .unity scene for a generated Runner game:
    /// player, camera, spawners, gimmick level content, UI, and the scene's
    /// single GameManager. Structural wiring only - GameSpec-driven numeric
    /// tuning happens at runtime via RunnerGameInitializer.
    /// </summary>
    public static class SceneGenerator
    {
        private const float GroundY = -1f;
        private const float ObstacleY = 0f;
        private const float CoinY = 1f;
        private const float TileWidth = 10f;

        private static Font cachedFont;

        public static string GenerateRunnerScene(GameSpec spec, RunnerPrefabSet prefabs, string sceneFolder)
        {
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            GameObject playerInstance = (GameObject)PrefabUtility.InstantiatePrefab(prefabs.Player, scene);
            playerInstance.transform.position = Vector3.zero;
            RunnerPlayerController playerController = playerInstance.GetComponent<RunnerPlayerController>();

            GameObject gameManagerGO = new GameObject("GameManager");
            GameManager gameManager = gameManagerGO.AddComponent<GameManager>();
            gameManager.SetGameId(spec.game.id);

            new GameObject("TapInput").AddComponent<TapInput>();

            GameObject cameraGO = new GameObject("Main Camera");
            cameraGO.tag = "MainCamera";
            cameraGO.transform.position = new Vector3(2f, 0f, -10f);
            Camera cam = cameraGO.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 5f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.1f, 0.1f, 0.15f);
            CameraFollow2D follow = cameraGO.AddComponent<CameraFollow2D>();
            follow.SetTarget(playerInstance.transform);

            GameObject groundSpawnerGO = new GameObject("GroundSpawner");
            GroundSpawner groundSpawner = groundSpawnerGO.AddComponent<GroundSpawner>();
            groundSpawner.SetReferences(prefabs.GroundTile, playerInstance.transform, TileWidth, GroundY);

            GameObject obstacleSpawnerGO = new GameObject("ObstacleSpawner");
            ObstacleSpawner obstacleSpawner = obstacleSpawnerGO.AddComponent<ObstacleSpawner>();
            obstacleSpawner.SetReferences(prefabs.Obstacle, playerInstance.transform, ObstacleY);

            GameObject coinSpawnerGO = new GameObject("CoinSpawner");
            CoinSpawner coinSpawner = coinSpawnerGO.AddComponent<CoinSpawner>();
            coinSpawner.SetReferences(prefabs.Coin, playerInstance.transform, CoinY);

            GameObject initializerGO = new GameObject("RunnerGameInitializer");
            RunnerGameInitializer initializer = initializerGO.AddComponent<RunnerGameInitializer>();
            initializer.SetTargets(playerController, obstacleSpawner, coinSpawner);

            LevelGenerator.ConfigureRunnerLevel(spec, playerInstance.transform, prefabs.GravityZone);

            BuildUI();
            EnsureEventSystem();

            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(sceneFolder));
            string sceneAssetPath = $"{sceneFolder}/{spec.game.id}.unity";
            EditorSceneManager.SaveScene(scene, sceneAssetPath);
            AddSceneToBuildSettings(sceneAssetPath);

            return sceneAssetPath;
        }

        private static void BuildUI()
        {
            GameObject canvasGO = new GameObject("Canvas");
            Canvas canvas = canvasGO.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            CanvasScaler scaler = canvasGO.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(720f, 1280f);
            scaler.matchWidthOrHeight = 0.5f;

            canvasGO.AddComponent<GraphicRaycaster>();

            Text scoreText = CreateText(canvasGO.transform, "ScoreText", "0", 64, TextAnchor.UpperLeft,
                new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f),
                new Vector2(300f, 100f), new Vector2(180f, -70f));

            GameObject panel = new GameObject("GameOverPanel", typeof(RectTransform));
            panel.transform.SetParent(canvasGO.transform, false);
            RectTransform panelRect = panel.GetComponent<RectTransform>();
            panelRect.anchorMin = Vector2.zero;
            panelRect.anchorMax = Vector2.one;
            panelRect.sizeDelta = Vector2.zero;
            panelRect.anchoredPosition = Vector2.zero;
            Image panelImage = panel.AddComponent<Image>();
            panelImage.color = new Color(0f, 0f, 0f, 0.75f);

            Text finalScoreText = CreateText(panel.transform, "FinalScoreText", "Score: 0", 56, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(500f, 80f), new Vector2(0f, 80f));

            Text bestScoreText = CreateText(panel.transform, "BestScoreText", "Best: 0", 40, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(500f, 60f), new Vector2(0f, 10f));

            GameObject buttonGO = new GameObject("RestartButton", typeof(RectTransform));
            buttonGO.transform.SetParent(panel.transform, false);
            RectTransform buttonRect = buttonGO.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0.5f, 0.5f);
            buttonRect.anchorMax = new Vector2(0.5f, 0.5f);
            buttonRect.pivot = new Vector2(0.5f, 0.5f);
            buttonRect.sizeDelta = new Vector2(280f, 100f);
            buttonRect.anchoredPosition = new Vector2(0f, -80f);
            Image buttonImage = buttonGO.AddComponent<Image>();
            buttonImage.color = new Color(0.2f, 0.6f, 0.9f);
            Button restartButton = buttonGO.AddComponent<Button>();

            CreateText(buttonGO.transform, "Label", "Restart", 40, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            panel.SetActive(false);

            GameObject controllerGO = new GameObject("GameUIController");
            GameUIController controller = controllerGO.AddComponent<GameUIController>();
            controller.SetReferences(scoreText, panel, finalScoreText, bestScoreText, restartButton);
        }

        private static Text CreateText(Transform parent, string name, string content, int fontSize, TextAnchor alignment,
            Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot, Vector2 sizeDelta, Vector2 anchoredPosition)
        {
            GameObject go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);

            RectTransform rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = pivot;
            rect.sizeDelta = sizeDelta;
            rect.anchoredPosition = anchoredPosition;

            Text text = go.AddComponent<Text>();
            text.text = content;
            text.font = GetDefaultFont();
            text.fontSize = fontSize;
            text.alignment = alignment;
            text.color = Color.white;

            return text;
        }

        private static Font GetDefaultFont()
        {
            if (cachedFont == null)
            {
                cachedFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            }

            return cachedFont;
        }

        private static void EnsureEventSystem()
        {
            if (Object.FindFirstObjectByType<EventSystem>() != null) return;

            GameObject eventSystemGO = new GameObject("EventSystem");
            eventSystemGO.AddComponent<EventSystem>();
            eventSystemGO.AddComponent<StandaloneInputModule>();
        }

        private static void AddSceneToBuildSettings(string sceneAssetPath)
        {
            var scenes = new System.Collections.Generic.List<EditorBuildSettingsScene>(EditorBuildSettings.scenes);
            if (scenes.Exists(s => s.path == sceneAssetPath)) return;

            scenes.Add(new EditorBuildSettingsScene(sceneAssetPath, true));
            EditorBuildSettings.scenes = scenes.ToArray();
        }
    }
}
