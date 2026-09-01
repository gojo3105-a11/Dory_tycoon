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
        private const string ButtonSpritePath = "Assets/Common/Art/UI/button.png";
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

            GameObject audioManagerGO = new GameObject("AudioManager");
            audioManagerGO.AddComponent<AudioSource>();
            audioManagerGO.AddComponent<AudioManager>();

            CreateVfxManager();

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

            BuildUI(spec.game.title);
            EnsureEventSystem(scene);

            Directory.CreateDirectory(EditorPaths.ToAbsolutePath(sceneFolder));
            string sceneAssetPath = $"{sceneFolder}/{spec.game.id}.unity";
            EditorSceneManager.SaveScene(scene, sceneAssetPath);
            AddSceneToBuildSettings(sceneAssetPath);

            return sceneAssetPath;
        }

        private static void BuildUI(string gameTitle)
        {
            GameObject canvasGO = new GameObject("Canvas");
            Canvas canvas = canvasGO.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            CanvasScaler scaler = canvasGO.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(720f, 1280f);
            scaler.matchWidthOrHeight = 0.5f;

            canvasGO.AddComponent<GraphicRaycaster>();

            GameObject safeAreaGO = new GameObject("SafeArea", typeof(RectTransform));
            safeAreaGO.transform.SetParent(canvasGO.transform, false);
            RectTransform safeAreaRect = safeAreaGO.GetComponent<RectTransform>();
            safeAreaRect.anchorMin = Vector2.zero;
            safeAreaRect.anchorMax = Vector2.one;
            safeAreaRect.sizeDelta = Vector2.zero;
            safeAreaRect.anchoredPosition = Vector2.zero;
            safeAreaGO.AddComponent<SafeAreaFitter>();

            Text scoreText = CreateText(safeAreaGO.transform, "ScoreText", "0", 64, TextAnchor.UpperLeft,
                new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f),
                new Vector2(300f, 100f), new Vector2(180f, -70f));

            GameObject panel = new GameObject("GameOverPanel", typeof(RectTransform));
            panel.transform.SetParent(safeAreaGO.transform, false);
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
            StyleButton(buttonImage, new Color(0.2f, 0.6f, 0.9f));
            Button restartButton = buttonGO.AddComponent<Button>();
            buttonGO.AddComponent<ButtonPunchFeedback>();

            CreateText(buttonGO.transform, "Label", "Restart", 40, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            GameObject homeButtonGO = new GameObject("HomeButton", typeof(RectTransform));
            homeButtonGO.transform.SetParent(panel.transform, false);
            RectTransform homeButtonRect = homeButtonGO.GetComponent<RectTransform>();
            homeButtonRect.anchorMin = new Vector2(0.5f, 0.5f);
            homeButtonRect.anchorMax = new Vector2(0.5f, 0.5f);
            homeButtonRect.pivot = new Vector2(0.5f, 0.5f);
            homeButtonRect.sizeDelta = new Vector2(280f, 90f);
            homeButtonRect.anchoredPosition = new Vector2(0f, -190f);
            Image homeButtonImage = homeButtonGO.AddComponent<Image>();
            StyleButton(homeButtonImage, new Color(0.55f, 0.55f, 0.6f));
            Button homeButton = homeButtonGO.AddComponent<Button>();
            homeButtonGO.AddComponent<ButtonPunchFeedback>();

            CreateText(homeButtonGO.transform, "Label", "Home", 36, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            GameObject shopButtonGO = new GameObject("ShopButton", typeof(RectTransform));
            shopButtonGO.transform.SetParent(panel.transform, false);
            RectTransform shopButtonRect = shopButtonGO.GetComponent<RectTransform>();
            shopButtonRect.anchorMin = new Vector2(0.5f, 0.5f);
            shopButtonRect.anchorMax = new Vector2(0.5f, 0.5f);
            shopButtonRect.pivot = new Vector2(0.5f, 0.5f);
            shopButtonRect.sizeDelta = new Vector2(280f, 90f);
            shopButtonRect.anchoredPosition = new Vector2(0f, -300f);
            Image shopButtonImage = shopButtonGO.AddComponent<Image>();
            StyleButton(shopButtonImage, new Color(0.9f, 0.6f, 0.2f));
            Button shopButton = shopButtonGO.AddComponent<Button>();
            shopButtonGO.AddComponent<ButtonPunchFeedback>();

            CreateText(shopButtonGO.transform, "Label", "상점", 36, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            CanvasGroup panelCanvasGroup = panel.AddComponent<CanvasGroup>();
            panelCanvasGroup.alpha = 0f;
            panel.AddComponent<PanelTransition>();
            panel.SetActive(false);

            // Button clicks (Restart/Home/Play/Shop) are all wired at runtime
            // by GameUIController/ShopController, not here: onClick.AddListener
            // registers a non-persistent listener, which is not serialized
            // into the saved scene, so wiring it at edit time would silently
            // produce dead buttons.
            BuildShopUI(safeAreaGO.transform, shopButton);
            (GameObject titlePanel, Text titleBestScoreText, Button playButton) = BuildTitleUI(safeAreaGO.transform, gameTitle);

            GameObject controllerGO = new GameObject("GameUIController");
            GameUIController controller = controllerGO.AddComponent<GameUIController>();
            controller.SetReferences(scoreText, panel, finalScoreText, bestScoreText, restartButton, homeButton,
                titlePanel, titleBestScoreText, playButton);
        }

        /// <summary>
        /// Title screen: game name, best score, and a Play button. Left
        /// active by default (unlike GameOverPanel/ShopPanel) since it is
        /// meant to be the first thing visible - GameUIController.Start()
        /// re-confirms this against GameManager's actual state anyway.
        /// </summary>
        private static (GameObject panel, Text bestScoreText, Button playButton) BuildTitleUI(Transform parentTransform, string gameTitle)
        {
            GameObject titlePanel = new GameObject("TitlePanel", typeof(RectTransform));
            titlePanel.transform.SetParent(parentTransform, false);
            RectTransform titleRect = titlePanel.GetComponent<RectTransform>();
            titleRect.anchorMin = Vector2.zero;
            titleRect.anchorMax = Vector2.one;
            titleRect.sizeDelta = Vector2.zero;
            titleRect.anchoredPosition = Vector2.zero;
            Image titleImage = titlePanel.AddComponent<Image>();
            titleImage.color = new Color(0.08f, 0.08f, 0.12f, 1f);

            CanvasGroup titleCanvasGroup = titlePanel.AddComponent<CanvasGroup>();
            titleCanvasGroup.alpha = 1f;
            titlePanel.AddComponent<PanelTransition>();

            CreateText(titlePanel.transform, "GameTitleText", gameTitle, 60, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(600f, 140f), new Vector2(0f, 220f));

            Text titleBestScoreText = CreateText(titlePanel.transform, "TitleBestScoreText", "Best: 0", 36, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(400f, 60f), new Vector2(0f, 120f));

            GameObject playButtonGO = new GameObject("PlayButton", typeof(RectTransform));
            playButtonGO.transform.SetParent(titlePanel.transform, false);
            RectTransform playButtonRect = playButtonGO.GetComponent<RectTransform>();
            playButtonRect.anchorMin = new Vector2(0.5f, 0.5f);
            playButtonRect.anchorMax = new Vector2(0.5f, 0.5f);
            playButtonRect.pivot = new Vector2(0.5f, 0.5f);
            playButtonRect.sizeDelta = new Vector2(320f, 110f);
            playButtonRect.anchoredPosition = new Vector2(0f, -60f);
            Image playButtonImage = playButtonGO.AddComponent<Image>();
            StyleButton(playButtonImage, new Color(0.2f, 0.75f, 0.35f));
            Button playButton = playButtonGO.AddComponent<Button>();
            playButtonGO.AddComponent<ButtonPunchFeedback>();

            CreateText(playButtonGO.transform, "Label", "PLAY", 44, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            return (titlePanel, titleBestScoreText, playButton);
        }

        private static void BuildShopUI(Transform parentTransform, Button openButton)
        {
            GameObject shopPanel = new GameObject("ShopPanel", typeof(RectTransform));
            shopPanel.transform.SetParent(parentTransform, false);
            RectTransform shopRect = shopPanel.GetComponent<RectTransform>();
            shopRect.anchorMin = Vector2.zero;
            shopRect.anchorMax = Vector2.one;
            shopRect.sizeDelta = Vector2.zero;
            shopRect.anchoredPosition = Vector2.zero;
            Image shopImage = shopPanel.AddComponent<Image>();
            shopImage.color = new Color(0.05f, 0.05f, 0.1f, 0.95f);

            CreateText(shopPanel.transform, "ShopTitle", "상점", 56, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(400f, 80f), new Vector2(0f, -60f));

            Text currencyText = CreateText(shopPanel.transform, "CurrencyText", "0", 40, TextAnchor.MiddleCenter,
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(300f, 60f), new Vector2(0f, -140f));

            CreateText(shopPanel.transform, "CoinMagnetLabel", "코인 자석", 36, TextAnchor.MiddleLeft,
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, 0.5f),
                new Vector2(260f, 60f), new Vector2(-140f, -240f));
            (Button coinMagnetButton, Text coinMagnetButtonLabel) = CreateShopButton(
                shopPanel.transform, "CoinMagnetButton", new Vector2(150f, -240f));

            CreateText(shopPanel.transform, "RedSkinLabel", "빨간 스킨", 36, TextAnchor.MiddleLeft,
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, 0.5f),
                new Vector2(260f, 60f), new Vector2(-140f, -320f));
            (Button redSkinButton, Text redSkinButtonLabel) = CreateShopButton(
                shopPanel.transform, "RedSkinButton", new Vector2(150f, -320f));

            (Button closeButton, Text closeButtonLabel) = CreateShopButton(
                shopPanel.transform, "CloseButton", new Vector2(0f, -420f), width: 260f);
            closeButtonLabel.text = "닫기";

            CanvasGroup shopCanvasGroup = shopPanel.AddComponent<CanvasGroup>();
            shopCanvasGroup.alpha = 0f;
            shopPanel.AddComponent<PanelTransition>();
            shopPanel.SetActive(false);

            GameObject shopControllerGO = new GameObject("ShopController");
            ShopController shopController = shopControllerGO.AddComponent<ShopController>();
            shopController.SetReferences(shopPanel, currencyText, openButton, coinMagnetButton, coinMagnetButtonLabel, redSkinButton, redSkinButtonLabel, closeButton);
        }

        private static (Button button, Text label) CreateShopButton(Transform parent, string name, Vector2 anchoredPosition, float width = 220f)
        {
            GameObject buttonGO = new GameObject(name, typeof(RectTransform));
            buttonGO.transform.SetParent(parent, false);
            RectTransform buttonRect = buttonGO.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0.5f, 1f);
            buttonRect.anchorMax = new Vector2(0.5f, 1f);
            buttonRect.pivot = new Vector2(0.5f, 0.5f);
            buttonRect.sizeDelta = new Vector2(width, 70f);
            buttonRect.anchoredPosition = anchoredPosition;
            Image buttonImage = buttonGO.AddComponent<Image>();
            StyleButton(buttonImage, new Color(0.2f, 0.6f, 0.9f));
            Button button = buttonGO.AddComponent<Button>();
            buttonGO.AddComponent<ButtonPunchFeedback>();

            Text label = CreateText(buttonGO.transform, "Label", string.Empty, 32, TextAnchor.MiddleCenter,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            return (button, label);
        }

        /// <summary>
        /// Applies the licensed 9-sliced button sprite. Buttons were an Image
        /// with NO sprite - a hard-cornered solid rectangle that read as
        /// unfinished next to the Kenney art around it. Sliced so the 4px
        /// outline and the 8px bottom depth lip keep their thickness at any
        /// button size; the border itself is set by SharedArtImporter, measured
        /// from the file rather than guessed.
        ///
        /// Falls back to the flat colour when no licensed art is present, so
        /// generation never produces an invisible button.
        /// </summary>
        private static void StyleButton(Image image, Color fallbackColor)
        {
            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(ButtonSpritePath);
            if (sprite == null)
            {
                image.color = fallbackColor;
                return;
            }

            image.sprite = sprite;
            image.type = Image.Type.Sliced;
            // Tinting multiplies, so the old mid-grey/orange fills would darken
            // the light-blue art into mud. White keeps the pack's own colour.
            image.color = Color.white;
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

        /// <summary>
        /// One persistent, manually-Emit()'d ParticleSystem for hit/collect
        /// bursts (see VfxManager). It is deliberately left looping and
        /// playing with rateOverTime at 0: that emits nothing by itself, but
        /// keeps the system simulating so a manual Emit() burst actually
        /// animates. A stopped system freezes the particles it is handed.
        ///
        /// MainModule.duration is intentionally not set - it is read-only in
        /// Unity's scripting API (assigning it is a compile error), and it is
        /// irrelevant to a looping system that never emits on its own clock.
        /// </summary>
        private static void CreateVfxManager()
        {
            GameObject vfxManagerGO = new GameObject("VfxManager");
            ParticleSystem particles = vfxManagerGO.AddComponent<ParticleSystem>();

            ParticleSystem.MainModule main = particles.main;
            main.playOnAwake = true;
            main.loop = true;
            main.startLifetime = 0.4f;
            main.startSpeed = 3f;
            main.startSize = 0.15f;
            main.simulationSpace = ParticleSystemSimulationSpace.World;

            ParticleSystem.EmissionModule emission = particles.emission;
            emission.rateOverTime = 0f;

            ParticleSystem.ShapeModule shape = particles.shape;
            shape.shapeType = ParticleSystemShapeType.Circle;
            shape.radius = 0.1f;

            // AddComponent'ing a ParticleSystem from script leaves its
            // renderer without a material, which renders nothing (or magenta)
            // - same class of bug as the Standard-vs-Unlit shader one, since
            // the generated scene has no Light either. Sprites/Default is
            // unlit and respects the per-particle startColor.
            // sharedMaterial, not material: assigning .material at edit time
            // makes Unity instantiate a copy and warn about leaking it into
            // the scene (same idiom as MainCharacterGenerator).
            ParticleSystemRenderer particleRenderer = vfxManagerGO.GetComponent<ParticleSystemRenderer>();
            Shader particleShader = Shader.Find("Sprites/Default");
            if (particleRenderer != null && particleShader != null)
            {
                particleRenderer.sharedMaterial = new Material(particleShader);
            }

            vfxManagerGO.AddComponent<VfxManager>();
        }

        /// <summary>
        /// Searches the generated scene's own hierarchy rather than calling
        /// Object.FindFirstObjectByType (obsolete in Unity 6.5, and it would
        /// also miss an EventSystem sitting inside the UI panels this
        /// generator deliberately saves disabled).
        /// </summary>
        private static void EnsureEventSystem(Scene scene)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                if (root.GetComponentInChildren<EventSystem>(true) != null) return;
            }

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
