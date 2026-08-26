using System.Collections;
using GameFactory.Core;
using GameFactory.Modules.GravitySwitch;
using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Auto-runs forward, jumps on tap while grounded, dies on Obstacle contact.</summary>
    [RequireComponent(typeof(Rigidbody2D))]
    [RequireComponent(typeof(Collider2D))]
    public class RunnerPlayerController : MonoBehaviour
    {
        [SerializeField] private float moveSpeed = 6f;
        [SerializeField] private float jumpPower = 10f;
        [SerializeField] private bool gravitySwitchEnabled;
        [SerializeField] private LayerMask groundLayer;
        [SerializeField] private Transform groundCheck;
        [SerializeField] private float groundCheckRadius = 0.15f;

        [SerializeField] private float hitStopDuration = 0.05f;
        [SerializeField] private float hitStopTimeScale = 0.05f;
        [SerializeField] private float hitShakeDuration = 0.2f;
        [SerializeField] private float hitShakeMagnitude = 0.15f;

        private Rigidbody2D body;
        private CameraFollow2D cameraFollow;
        private bool isGrounded;
        private bool isDead;

        private static AudioClip jumpClip;

        /// <summary>Applies GameSpec-driven tuning. Called at runtime by RunnerGameInitializer.</summary>
        public void Configure(float speed, float jump, bool useGravitySwitch)
        {
            moveSpeed = speed;
            jumpPower = jump;
            gravitySwitchEnabled = useGravitySwitch;
        }

        /// <summary>Wires structural references. Called at edit time by SceneGenerator.</summary>
        public void SetGroundCheck(Transform check, LayerMask layer)
        {
            groundCheck = check;
            groundLayer = layer;
        }

        private void Awake()
        {
            body = GetComponent<Rigidbody2D>();
            cameraFollow = Camera.main != null ? Camera.main.GetComponent<CameraFollow2D>() : null;
            GravitySwitchController.ResetToDefault();
        }

        private void OnEnable()
        {
            TapInput.Tapped += HandleTap;
        }

        private void OnDisable()
        {
            TapInput.Tapped -= HandleTap;
        }

        private void FixedUpdate()
        {
            if (groundCheck != null)
            {
                isGrounded = Physics2D.OverlapCircle(groundCheck.position, groundCheckRadius, groundLayer);
            }

            // Ground check above still runs on the title screen so the
            // character visibly stands on the start line instead of hovering;
            // only forward movement itself waits for Play.
            if (isDead || GameManager.Instance == null || GameManager.Instance.CurrentState != GameManager.GameState.Playing) return;

            body.linearVelocity = new Vector2(moveSpeed, body.linearVelocity.y);
        }

        private void HandleTap()
        {
            if (isDead || !isGrounded) return;
            if (GameManager.Instance == null || GameManager.Instance.CurrentState != GameManager.GameState.Playing) return;

            bool inverted = gravitySwitchEnabled && GravitySwitchController.IsInverted;
            float jumpDirection = inverted ? -1f : 1f;
            body.linearVelocity = new Vector2(body.linearVelocity.x, jumpDirection * jumpPower);

            if (jumpClip == null) jumpClip = ProceduralTone.Sine("SFX_Jump", 620f, 0.12f);
            AudioManager.Instance?.PlaySfx(jumpClip);
            if (SettingsSystem.VibrationEnabled) Handheld.Vibrate();
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            if (other.CompareTag("Obstacle"))
            {
                Die();
            }
        }

        private void Die()
        {
            if (isDead) return;

            isDead = true;
            body.linearVelocity = Vector2.zero;
            cameraFollow?.Shake(hitShakeDuration, hitShakeMagnitude);
            StartCoroutine(HitStop(hitStopDuration, hitStopTimeScale));
            if (SettingsSystem.VibrationEnabled) Handheld.Vibrate();
            GameManager.Instance.TriggerGameOver();
        }

        /// <summary>Briefly slows time on impact, then restores it - purely a game-feel beat, not a state change.</summary>
        private IEnumerator HitStop(float duration, float slowTimeScale)
        {
            Time.timeScale = slowTimeScale;
            yield return new WaitForSecondsRealtime(duration);
            Time.timeScale = 1f;
        }
    }
}
