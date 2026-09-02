using System.Collections;
using GameFactory.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace GameFactory.Tests.PlayMode
{
    /// <summary>
    /// Exercises the actual generated Factory Runner scene. Requires
    /// GameFactoryGenerator to have already produced
    /// Assets/GeneratedGames/game01/Scenes/game01.unity
    /// (and registered it in Build Settings) - run the generator before
    /// running this suite, exactly as the CI pipeline does.
    /// </summary>
    public class FactoryRunnerPlayModeTests
    {
        private const string SceneName = "game01";

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            SceneManager.LoadScene(SceneName);
            yield return null;
        }

        [UnityTest]
        public IEnumerator GeneratedScene_HasGameManagerAndPlayer()
        {
            Assert.IsNotNull(GameManager.Instance, "GameManager.Instance should be set after scene load.");
            Assert.IsNotNull(GameObject.FindGameObjectWithTag("Player"), "Scene should contain a Player-tagged object.");
            yield return null;
        }

        /// <summary>
        /// A fresh scene load now lands on the title screen (GameState.Ready)
        /// instead of auto-starting - see GameManager.Awake/GameUIController's
        /// Play button. The state-machine tests below are about Playing/
        /// GameOver behavior specifically, so each calls StartGame() first to
        /// simulate the player pressing Play, same as they did implicitly
        /// when the scene auto-started.
        /// </summary>
        [UnityTest]
        public IEnumerator GameStartsOnTitleScreenInReadyState()
        {
            yield return null;

            Assert.AreEqual(GameManager.GameState.Ready, GameManager.Instance.CurrentState);
            Assert.AreEqual(0, GameManager.Instance.Score);
        }

        [UnityTest]
        public IEnumerator StartGame_EntersPlayingStateWithZeroScore()
        {
            yield return null;
            GameManager.Instance.StartGame();
            yield return null;

            Assert.AreEqual(GameManager.GameState.Playing, GameManager.Instance.CurrentState);
            Assert.AreEqual(0, GameManager.Instance.Score);
        }

        [UnityTest]
        public IEnumerator AddScore_IncreasesScoreAndFiresEvent()
        {
            yield return null;
            GameManager.Instance.StartGame();
            yield return null;

            int reported = -1;
            GameManager.Instance.ScoreChanged += s => reported = s;

            GameManager.Instance.AddScore(5);
            yield return null;

            Assert.AreEqual(5, GameManager.Instance.Score);
            Assert.AreEqual(5, reported);
        }

        [UnityTest]
        public IEnumerator SetScore_LowerOrEqualValue_IsIgnored()
        {
            yield return null;
            GameManager.Instance.StartGame();
            GameManager.Instance.SetScore(10);
            yield return null;

            int eventCount = 0;
            GameManager.Instance.ScoreChanged += _ => eventCount++;

            GameManager.Instance.SetScore(9);
            GameManager.Instance.SetScore(10);
            yield return null;

            Assert.AreEqual(10, GameManager.Instance.Score);
            Assert.AreEqual(0, eventCount, "Ignored values should not fire ScoreChanged.");
        }

        [UnityTest]
        public IEnumerator AddCoins_IncreasesCoinsAndFiresEvent_UntilGameOver()
        {
            yield return null;
            GameManager.Instance.SetGameId($"playmode_add_coins_{System.Guid.NewGuid():N}");
            GameManager.Instance.StartGame();
            yield return null;

            int reported = -1;
            int eventCount = 0;
            GameManager.Instance.CoinsChanged += coins =>
            {
                reported = coins;
                eventCount++;
            };

            GameManager.Instance.AddCoins(4);
            yield return null;

            Assert.AreEqual(4, GameManager.Instance.Coins);
            Assert.AreEqual(4, reported);
            Assert.AreEqual(1, eventCount);

            GameManager.Instance.TriggerGameOver();
            GameManager.Instance.AddCoins(6);
            yield return null;

            Assert.AreEqual(4, GameManager.Instance.Coins, "Coins should not change once the run is over.");
            Assert.AreEqual(1, eventCount, "Ignored coin additions should not fire CoinsChanged.");
        }

        [UnityTest]
        public IEnumerator StartGame_ResetsScoreAndCoinsToZero()
        {
            yield return null;
            GameManager.Instance.StartGame();
            GameManager.Instance.AddScore(7);
            GameManager.Instance.AddCoins(3);
            yield return null;

            GameManager.Instance.StartGame();
            yield return null;

            Assert.AreEqual(0, GameManager.Instance.Score);
            Assert.AreEqual(0, GameManager.Instance.Coins);
        }

        [UnityTest]
        public IEnumerator TriggerGameOver_AddsCoinsNotScoreToSavedCurrency()
        {
            yield return null;
            string gameId = $"playmode_currency_{System.Guid.NewGuid():N}";
            GameManager.Instance.SetGameId(gameId);
            SaveSystem.SaveInt(gameId, ShopKeys.Currency, 11);
            GameManager.Instance.StartGame();
            GameManager.Instance.SetScore(100);
            GameManager.Instance.AddCoins(4);
            yield return null;

            GameManager.Instance.TriggerGameOver();
            yield return null;

            Assert.AreEqual(15, SaveSystem.GetInt(gameId, ShopKeys.Currency));
        }

        [UnityTest]
        public IEnumerator TriggerGameOver_ReportsRecordStateFromBeforeRunEnded()
        {
            yield return null;
            string gameId = $"playmode_best_{System.Guid.NewGuid():N}";
            GameManager.Instance.SetGameId(gameId);
            SaveSystem.SaveBestScore(gameId, 10);
            GameManager.Instance.StartGame();
            GameManager.Instance.SetScore(15);
            yield return null;

            GameManager.Instance.TriggerGameOver();
            yield return null;

            Assert.AreEqual(10, GameManager.Instance.PreviousBest);
            Assert.IsTrue(GameManager.Instance.IsNewBest);

            GameManager.Instance.StartGame();
            GameManager.Instance.SetScore(12);
            GameManager.Instance.TriggerGameOver();
            yield return null;

            Assert.AreEqual(15, GameManager.Instance.PreviousBest);
            Assert.IsFalse(GameManager.Instance.IsNewBest);
        }

        [UnityTest]
        public IEnumerator TriggerGameOver_ChangesStateAndFiresEvent()
        {
            yield return null;
            GameManager.Instance.StartGame();
            yield return null;

            bool fired = false;
            GameManager.Instance.GameOver += (finalScore, best) => fired = true;

            GameManager.Instance.TriggerGameOver();
            yield return null;

            Assert.AreEqual(GameManager.GameState.GameOver, GameManager.Instance.CurrentState);
            Assert.IsTrue(fired);
        }

        [UnityTest]
        public IEnumerator AddScore_AfterGameOver_IsIgnored()
        {
            yield return null;
            GameManager.Instance.StartGame();
            yield return null;

            GameManager.Instance.AddScore(3);
            GameManager.Instance.TriggerGameOver();
            yield return null;

            GameManager.Instance.AddScore(10);
            yield return null;

            Assert.AreEqual(3, GameManager.Instance.Score, "Score should not change once the run is over.");
        }
    }
}
