using GameFactory.Core.Spec;
using NUnit.Framework;

namespace GameFactory.Tests.EditMode
{
    /// <summary>Pure-C# tests for GameSpec parsing/validation - no scene or Play mode required.</summary>
    public class GameSpecTests
    {
        private const string SampleJson = @"{
            ""game"": { ""id"": ""game01"", ""title"": ""Factory Runner"", ""genre"": ""Runner"" },
            ""player"": { ""moveSpeed"": 6, ""jumpPower"": 10 },
            ""mechanics"": { ""jump"": true, ""doubleJump"": false, ""dash"": false, ""wallJump"": false, ""gravitySwitch"": true, ""teleport"": false, ""timeSlow"": false },
            ""level"": { ""levelCount"": 1, ""difficulty"": ""Medium"", ""procedural"": true, ""length"": 120 },
            ""enemy"": { ""enabled"": false, ""types"": 0 },
            ""special"": { ""mechanic"": ""GravitySwitch"" },
            ""theme"": { ""environment"": ""Factory"", ""character"": ""Slime"" }
        }";

        [Test]
        public void LoadFromJson_ParsesAllFields()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");

            Assert.AreEqual("game01", spec.game.id);
            Assert.AreEqual("Runner", spec.game.genre);
            Assert.AreEqual(6f, spec.player.moveSpeed);
            Assert.AreEqual(10f, spec.player.jumpPower);
            Assert.IsTrue(spec.mechanics.gravitySwitch);
            Assert.AreEqual(120f, spec.level.length);
            Assert.AreEqual("GravitySwitch", spec.special.mechanic);
        }

        [Test]
        public void LoadFromJson_EmptyString_Throws()
        {
            Assert.Throws<GameSpecException>(() => GameSpecParser.LoadFromJson(""));
        }

        [Test]
        public void LoadFromJson_MissingGameId_Throws()
        {
            Assert.Throws<GameSpecException>(() => GameSpecParser.LoadFromJson("{}"));
        }

        [Test]
        public void Validate_SampleSpec_IsValid()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");

            ValidationResult result = GameSpecValidator.Validate(spec);

            Assert.IsTrue(result.IsValid, string.Join(", ", result.Errors));
        }

        [Test]
        public void Validate_InvalidId_ReportsError()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");
            spec.game.id = "Invalid ID!";

            ValidationResult result = GameSpecValidator.Validate(spec);

            Assert.IsFalse(result.IsValid);
        }

        [Test]
        public void Validate_UnknownGenre_ReportsError()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");
            spec.game.genre = "NotAGenre";

            ValidationResult result = GameSpecValidator.Validate(spec);

            Assert.IsFalse(result.IsValid);
        }

        [Test]
        public void Validate_ZeroMoveSpeed_ReportsError()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");
            spec.player.moveSpeed = 0f;

            ValidationResult result = GameSpecValidator.Validate(spec);

            Assert.IsFalse(result.IsValid);
        }

        [Test]
        public void Validate_UnknownDifficulty_ReportsError()
        {
            GameSpec spec = GameSpecParser.LoadFromJson(SampleJson, "test");
            spec.level.difficulty = "Extreme";

            ValidationResult result = GameSpecValidator.Validate(spec);

            Assert.IsFalse(result.IsValid);
        }
    }
}
