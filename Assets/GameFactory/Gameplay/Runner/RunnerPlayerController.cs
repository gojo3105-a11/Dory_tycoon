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

        private Rigidbody2D body;
        private bool isGrounded;
        private bool isDead;

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
            if (isDead) return;

            body.linearVelocity = new Vector2(moveSpeed, body.linearVelocity.y);

            if (groundCheck != null)
            {
                isGrounded = Physics2D.OverlapCircle(groundCheck.position, groundCheckRadius, groundLayer);
            }
        }

        private void HandleTap()
        {
            if (isDead || !isGrounded) return;

            bool inverted = gravitySwitchEnabled && GravitySwitchController.IsInverted;
            float jumpDirection = inverted ? -1f : 1f;
            body.linearVelocity = new Vector2(body.linearVelocity.x, jumpDirection * jumpPower);
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
            GameManager.Instance.TriggerGameOver();
        }
    }
}
