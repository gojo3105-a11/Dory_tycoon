using GameFactory.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GameFactory.UI
{
    /// <summary>
    /// Single UI orchestrator for a generated game: live score, and on game
    /// over a panel with the final/best score and a restart button. Reads
    /// only GameManager's public events/API - it holds no gameplay state.
    /// </summary>
    public class GameUIController : MonoBehaviour
    {
        [SerializeField] private Text scoreText;
        [SerializeField] private GameObject gameOverPanel;
        [SerializeField] private Text finalScoreText;
        [SerializeField] private Text bestScoreText;
        [SerializeField] private Button restartButton;
        [SerializeField] private Button homeButton;
        [SerializeField] private GameObject titlePanel;
        [SerializeField] private Text titleBestScoreText;
        [SerializeField] private Button playButton;

        private PanelTransition gameOverTransition;
        private PanelTransition titleTransition;

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetReferences(Text score, GameObject gameOver, Text finalScore, Text bestScore, Button restart, Button home,
            GameObject title, Text titleBestScore, Button play)
        {
            scoreText = score;
            gameOverPanel = gameOver;
            finalScoreText = finalScore;
            bestScoreText = bestScore;
            restartButton = restart;
            homeButton = home;
            titlePanel = title;
            titleBestScoreText = titleBestScore;
            playButton = play;
        }

        private void Start()
        {
            gameOverTransition = gameOverPanel != null ? gameOverPanel.GetComponent<PanelTransition>() : null;
            titleTransition = titlePanel != null ? titlePanel.GetComponent<PanelTransition>() : null;

            if (gameOverPanel != null) gameOverPanel.SetActive(false);
            if (restartButton != null) restartButton.onClick.AddListener(HandleRestartClicked);
            if (homeButton != null) homeButton.onClick.AddListener(HandleHomeClicked);
            if (playButton != null) playButton.onClick.AddListener(HandlePlayClicked);

            GameManager manager = GameManager.Instance;
            if (manager == null) return;

            manager.ScoreChanged += HandleScoreChanged;
            manager.GameOver += HandleGameOver;
            HandleScoreChanged(manager.Score);
            RefreshTitleBestScore();

            // Title starts on top and covers the HUD/gameplay behind it (it
            // is the last sibling added under Canvas by SceneGenerator, so it
            // draws last) until Play is pressed - the character still stands
            // on the start line since physics/ground-check keep running.
            if (titlePanel != null) titlePanel.SetActive(manager.CurrentState != GameManager.GameState.Playing);
        }

        private void OnDestroy()
        {
            GameManager manager = GameManager.Instance;
            if (manager == null) return;

            manager.ScoreChanged -= HandleScoreChanged;
            manager.GameOver -= HandleGameOver;
        }

        private void HandleScoreChanged(int score)
        {
            if (scoreText != null) scoreText.text = score.ToString();
        }

        private void HandleGameOver(int finalScore, int bestScore)
        {
            if (gameOverTransition != null) gameOverTransition.Show();
            else if (gameOverPanel != null) gameOverPanel.SetActive(true);

            if (finalScoreText != null) finalScoreText.text = $"Score: {finalScore}";
            if (bestScoreText != null) bestScoreText.text = $"Best: {bestScore}";
        }

        private void HandleRestartClicked()
        {
            GameManager.Instance?.RestartGame();
        }

        /// <summary>Reloads without requesting an auto-start, so the reload lands back on the title screen.</summary>
        private void HandleHomeClicked()
        {
            SceneController.ReloadCurrent();
        }

        private void HandlePlayClicked()
        {
            if (titleTransition != null) titleTransition.Hide();
            else if (titlePanel != null) titlePanel.SetActive(false);

            GameManager.Instance?.StartGame();
        }

        private void RefreshTitleBestScore()
        {
            if (titleBestScoreText == null || GameManager.Instance == null) return;
            titleBestScoreText.text = $"Best: {SaveSystem.GetBestScore(GameManager.Instance.GameId)}";
        }
    }
}
